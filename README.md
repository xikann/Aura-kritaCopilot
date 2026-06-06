# Aura Krita AI Copilot

```text
 /\_/\  
( o.o ) 
 > ^ <
```

Aura is an AI copilot plugin for Krita. It helps you quickly process line art and add flat colors using AI models running on a local backend.

## Features
- **Perfect for messy sketches**: It works great with messy, broken, or unclosed sketch lines.
- **No more color leaking**: We completely removed the old Watershed algorithm.
- **Smart Edge Snapping**: We use a math method called "Guided Filter" to make the AI flat colors perfectly stick to your sketch lines!

## Folders
- `ai_copilot/`: The Krita UI plugin folder.
- `server.py`: The backend engine (runs with FastAPI).
- `deploy.py`: A script to easily install the plugin into Krita.
- `anime-segmentation/`: The core AI model code for image cutting.

## Model Download
> **Note**: GitHub does not allow very large files. You need to download these model weights yourself and put them in the main folder:
> - `isnetis.ckpt`
> - `mobile_sam.pt`

## Acknowledgements

- The AI image cutting part (`anime-segmentation` folder) is based on [skytnt/anime-segmentation](https://github.com/skytnt/anime-segmentation). We kept their original code and license. A big thank you to the original author for their great open-source work!
- Thanks to the Krita community for making such an amazing drawing app and providing great plugin support.
