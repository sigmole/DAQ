from qt import Ui_mainWindow
from PyQt5 import QtWidgets, QtCore
from PyQt5.Qt import *
import sys
global data_list

class Window(QMainWindow, Ui_mainWindow):
    def __init__(self):
        super(Window, self).__init__()
        self.setupUi(self)

    def data(self):
        global data_list
        data_list = []
        for i in range(3,24):
            for j in range(4):
                data_list.append(4*i+j)
                data_list.append('_')
            data_list.append('|')


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = Window()
    window.show()
    window.data()
    print(data_list)
    sys.exit(app.exec_())

