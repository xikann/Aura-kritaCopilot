from PyQt5.QtGui import QImage
from PyQt5.QtCore import QByteArray, QBuffer, QIODevice
import sys

ba = QByteArray(b'\xff' * (100*100*4))
def create_image(ba):
    # This simulates pixel_data.data()
    return QImage(ba.data(), 100, 100, QImage.Format_RGBA8888)

image = create_image(ba)
buffer = QBuffer()
buffer.open(QIODevice.WriteOnly)
image.save(buffer, "PNG")
data = buffer.data()
print("Length:", len(data))
# Check if it saved a valid PNG header
if data.startswith(b'\x89PNG'):
    print("Valid PNG header")
else:
    print("Invalid PNG header!")
