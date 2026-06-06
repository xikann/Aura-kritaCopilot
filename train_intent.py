"""
Krita AI Copilot 意图提取模型微调脚本 (纯底层 PyTorch 实现 + 极致显存优化)
本脚本展示了如何在 8GB 显存设备上，通过手写训练循环、FP16 半精度、LoRA 和微批次
来微调 Qwen2.5-0.5B 大模型。
"""

import os
import torch
import torch.nn as nn
from transformers import AutoModelForCausalLM, AutoTokenizer
from torch.optim import AdamW
from peft import get_peft_model, LoraConfig, TaskType

def main():
    # ---------------------------------------------------------
    # 1. 基础设置与设备分配
    # ---------------------------------------------------------
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[*] 当前使用设备: {device}")
    if device.type == "cuda":
        print(f"[*] GPU型号: {torch.cuda.get_device_name(0)}")

    model_id = "Qwen/Qwen2.5-0.5B"
    print(f"[*] 正在加载分词器: {model_id} ...")
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print(f"[*] 正在加载模型权重(半精度 FP16)到 {device} ...")
    # 【显存优化 1】: 强制以 FP16 加载模型，直接砍掉一半显存
    model = AutoModelForCausalLM.from_pretrained(
        model_id, 
        trust_remote_code=True,
        torch_dtype=torch.float16
    )
    
    # 【显存优化 2】: 开启梯度检查点，用计算时间换取显存空间
    model.gradient_checkpointing_enable()

    # 【显存优化 3】: 引入 LoRA 冻结绝大多数权重，只训练少量适配器参数
    print("[*] 正在注入 LoRA 适配器...")
    peft_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        inference_mode=False,
        r=8,
        lora_alpha=32,
        lora_dropout=0.1,
        target_modules=["q_proj", "v_proj"]
    )
    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()
    
    model.to(device)
    model.train()

    # ---------------------------------------------------------
    # 2. 极简硬编码数据集 (学术演示专用)
    # ---------------------------------------------------------
    raw_data = [
        # --- 【正经填色指令】 ---
        ("帮我给苹果铺红底", '{"action_type": "fill_color", "target": "苹果", "target_en": "apple", "color_hex": "#FF0000"}'),
        ("请将选区内的头发填充为深棕色", '{"action_type": "fill_color", "target": "头发", "target_en": "hair", "color_hex": "#654321"}'),
        ("给衣服上个灰色", '{"action_type": "fill_color", "target": "衣服", "target_en": "clothes", "color_hex": "#808080"}'),
        ("这块区域我要纯黑", '{"action_type": "fill_color", "target": "选区", "target_en": "selection", "color_hex": "#000000"}'),
        ("给蝴蝶结区域上个藏青色", '{"action_type": "fill_color", "target": "蝴蝶结", "target_en": "bow", "color_hex": "#000080"}'),
        
        # --- 【暴躁/极简口癖指令】 ---
        ("卧槽这苹果太白了，赶紧变红", '{"action_type": "fill_color", "target": "苹果", "target_en": "apple", "color_hex": "#FF0000"}'),
        ("脸部涂白", '{"action_type": "fill_color", "target": "脸部", "target_en": "face", "color_hex": "#FFFFFF"}'),
        ("给老子把这坨草稿涂成灰色", '{"action_type": "fill_color", "target": "草稿", "target_en": "draft", "color_hex": "#808080"}'),
        ("圈住的地方来个紫色", '{"action_type": "fill_color", "target": "圈住的地方", "target_en": "selection", "color_hex": "#800080"}'),
         
        # --- 【非填色指令 (防御性路由，防止乱涂色)】 ---
        ("帮我把图层删了", '{"action_type": "delete_layer", "target": "当前图层", "target_en": "current layer", "color_hex": ""}'),
        ("建个名叫线稿的新图层", '{"action_type": "create_layer", "target": "线稿", "target_en": "lineart", "color_hex": ""}'),
        ("线稿加粗", '{"action_type": "bold_lines", "target": "线稿", "target_en": "lineart", "color_hex": ""}')
    ]

    prompt_template = "提取颜色意图并输出JSON。指令: {user_input}\n输出: "

    input_ids_list = []
    labels_list = []
    attention_mask_list = []

    print("\n[*] 正在进行手动分词与数据编码...")
    for user_text, target_json in raw_data:
        full_text = prompt_template.format(user_input=user_text) + target_json + tokenizer.eos_token
        
        tokenized = tokenizer(full_text, truncation=True, max_length=128, padding="max_length", return_tensors="pt")
        
        prompt_text = prompt_template.format(user_input=user_text)
        prompt_len = len(tokenizer(prompt_text).input_ids)
        
        labels = tokenized["input_ids"].clone()
        labels[0, :prompt_len] = -100

        input_ids_list.append(tokenized["input_ids"][0])
        labels_list.append(labels[0])
        attention_mask_list.append(tokenized["attention_mask"][0])

    dataset_size = len(input_ids_list)
    
    # ---------------------------------------------------------
    # 3. 优化器与损失函数设置
    # ---------------------------------------------------------
    optimizer = AdamW(model.parameters(), lr=5e-5)
    loss_fn = nn.CrossEntropyLoss(ignore_index=-100)

    # ---------------------------------------------------------
    # 4. 核心训练循环 (Training Loop - Micro-Batching)
    # ---------------------------------------------------------
    epochs = 10
    # 【显存优化 4】: 微批次训练防浪涌
    batch_size = 2 
    
    print(f"\n[*] 开始防浪涌训练循环 (Mini-Batching, batch_size={batch_size})...")
    for epoch in range(epochs):
        epoch_loss = 0.0
        batches = 0
        
        for i in range(0, dataset_size, batch_size):
            # 提取切片构造当前 batch
            batch_input_ids = torch.stack(input_ids_list[i:i+batch_size]).to(device)
            batch_labels = torch.stack(labels_list[i:i+batch_size]).to(device)
            batch_attention_mask = torch.stack(attention_mask_list[i:i+batch_size]).to(device)
            
            optimizer.zero_grad()
            
            outputs = model(
                input_ids=batch_input_ids,
                attention_mask=batch_attention_mask
            )
            logits = outputs.logits
            
            shift_logits = logits[..., :-1, :].contiguous()
            shift_labels = batch_labels[..., 1:].contiguous()
            
            flat_logits = shift_logits.view(-1, shift_logits.size(-1))
            flat_labels = shift_labels.view(-1)
            
            loss = loss_fn(flat_logits, flat_labels)
            
            loss.backward()
            optimizer.step()
            
            epoch_loss += loss.item()
            batches += 1
            
            # 【显存优化 5】: 每批次立刻释放无用张量，清空缓存
            del batch_input_ids, batch_labels, batch_attention_mask, outputs, logits, shift_logits, shift_labels, flat_logits, flat_labels, loss
            torch.cuda.empty_cache()
            
        avg_loss = epoch_loss / batches
        print(f"    Epoch {epoch+1:02d}/{epochs} - Avg Loss: {avg_loss:.4f}")

    # ---------------------------------------------------------
    # 5. 保存模型与显存清理
    # ---------------------------------------------------------
    save_path = "./checkpoints/intent_model_0.5b_lora"
    os.makedirs(save_path, exist_ok=True)
    print(f"\n[*] 训练完成！正在保存 LoRA 权重到: {save_path}")
    
    model.save_pretrained(save_path)
    tokenizer.save_pretrained(save_path)
    
    print("[*] 清理 GPU 显存...")
    del model
    del optimizer
    torch.cuda.empty_cache()
    
    print("[*] 脚本执行完毕。")

if __name__ == "__main__":
    main()
