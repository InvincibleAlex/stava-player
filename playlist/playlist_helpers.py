import os
from PyQt6.QtGui import QPixmap, QPainter, QColor, QIcon
from core.utils import IconHelper

class PlaylistHelpers:
    @staticmethod
    def set_action_icon_colored(action, filename, color_hex):
        """ Colorează o iconiță pentru un QAction """
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_dir, 'icons', filename)
        icon = IconHelper.get_colored_icon(icon_path, color_hex)
        action.setIcon(icon)
