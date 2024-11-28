# 版本:v1.0
# 应变采样率:2k 应变分辨率:16bit（2Byte）
# 每个测量元组=当前时间（2Byte）+采样数据（4Byte）+标识符（4Byte）+测点（2Byte）=12Byte
# 每个客户端每次发送的数据流中包含：200个测量元组（采集约为100ms）
# 数据流格式：测点_时间_x数据_y数据|测点_时间_x数据_y数据|...|测点_时间_x数据_y数据|
# 警告：目前不能选择数据表;如果数据表中主键（时间）重复会报错；客户端连接没法while true
# 警告：每次实验前记得清空数据表；fifo容量期望240MB； 线程优先级设置; 现在是共用一个fifo,共用一个拆包线程

from qt import Ui_mainWindow
from socket import *
from PyQt5 import QtWidgets, QtCore
from PyQt5.Qt import *
from PyQt5.QtChart import *
from scapy.all import *

import pymysql
import sys

global x_max, x_min, y_min, y_max, x_range
global ip, port
resolution = 0.0005
color_list = [(0, 0, 255), (0, 255, 0)]
data_size = 2048

# 创建通道fifo
fifo_01 = bytearray(0)
mutex = QMutex()  # 创建互斥锁

# 建立mysql连接
connection_sql = pymysql.connect(
    host='localhost',  # MySQL 主机
    user='root',  # MySQL 用户名
    password='012766',  # MySQL 密码
    database='points_db'  # 目标数据库
)
cursor = connection_sql.cursor()
sql_01 = "insert into point_01 (time, x_data, y_data) VALUES (%s, %s, %s)"
sql_02 = "insert into point_02 (time, x_data, y_data) VALUES (%s, %s, %s)"


def unpack(buffer):
    global x_max, x_min, y_min, y_max, x_range
    delimiter_unit = b'|'  # 单元分隔符
    delimiter_field = b'_'  # 字段分隔符
    print("开始拆包")
    while delimiter_unit in buffer:
        print("succeed_1")
        unit, buffer = buffer.split(delimiter_unit, 1)
        if delimiter_field in unit:
            print("succeed_2")
            point_num, unit = unit.split(delimiter_field, 1)
            if delimiter_field in unit and len(point_num) > 0:
                time, unit = unit.split(delimiter_field, 1)
                print("succeed_3")
                if delimiter_field in unit:
                    x_data, y_data = unit.split(delimiter_field, 1)
                    point_num = int(point_num)
                    time = float(time)
                    x_data = float(x_data)
                    y_data = float(y_data)
                    print(point_num)
                    # 将数据存储到本地数据库中
                    if point_num == 1:
                        cursor.execute(sql_01, (time, x_data, y_data))
                    elif point_num == 2:
                        cursor.execute(sql_02, (time, x_data, y_data))

                    # 将获取的客户端数据添加到对应的图表中
                    window.chart_list[point_num].series[0].append(time, x_data)
                    window.chart_list[point_num].series[1].append(time, y_data)
                    if time >= x_max:
                        window.chart_list[point_num].series[0].remove(0)
                        window.chart_list[point_num].series[1].remove(0)
                        x_max = time
                        x_min = x_max - x_range
                        window.chart_list[point_num].axisX.setRange(x_min, x_max)
                else:
                    print(f"Storage failed")
            else:
                print(f"Storage failed")
    connection_sql.commit()


class Chart(QtWidgets.QWidget):
    def __init__(self):
        super(Chart, self).__init__()
        self.axisX = None
        self.series = None
        global x_min, x_max, y_min, y_max, x_range
        x_min = 0
        x_max = 0.1
        y_min = 0
        y_max = 100
        x_range = 0.1  # 时间观察窗为0.1s

        # 设置QChart对象
        self.chart = QChart()
        self.chart.setTitle("管道应变图")
        # 设置线条
        self.series = [QLineSeries() for i in range(2)]  # 2个方向
        for j in range(2):
            if j == 0:
                self.series[j].setName("x方向")
                self.series[j].setColor(QColor(color_list[0][0], color_list[0][1], color_list[0][2]))
            else:
                self.series[j].setName("y方向")
                self.series[j].setColor(QColor(color_list[1][0], color_list[1][1], color_list[1][2]))
        # 设置坐标轴
        self.axisX = QValueAxis()
        self.axisX.setRange(x_min, x_max)
        self.axisX.setTitleText("时间（s）")
        self.axisY = QValueAxis()
        self.axisY.setTitleText("应变（με）")
        self.axisY.setRange(y_min, y_max)

        self.chart.addAxis(self.axisX, Qt.AlignBottom)
        self.chart.addAxis(self.axisY, Qt.AlignLeft)
        self.chart.addSeries(self.series[0])
        self.chart.addSeries(self.series[1])
        self.series[0].attachAxis(self.axisX)
        self.series[1].attachAxis(self.axisX)
        self.series[0].attachAxis(self.axisY)
        self.series[1].attachAxis(self.axisY)


class ClientConnect(QThread):
    def __init__(self):
        super(ClientConnect, self).__init__()
        self.client_num = 0
        self.address_client = None
        self.client_socket = None

    def run(self):
        window.label_4.setText("等待连接")
        unpack_data = UnpackData() # 开线程位置？
        unpack_data.start()
        unpack_data.setPriority(QThread.LowPriority)
        while True:
            self.client_socket, self.address_client = window.sock.accept()
            receive_thread = ReceiveData(self.client_socket, self.address_client)
            receive_thread.start()
            receive_thread.setPriority(QThread.NormalPriority)
            client_threads.append(receive_thread)  # 是否是不同的独立线程
            self.client_num += 1
            window.label_4.setText("已连接%d个客户端" % self.client_num)


class ReceiveData(QThread):
    def __init__(self, client_socket, client_address):
        super(ReceiveData, self).__init__()
        self.buffer = bytearray(0)
        self.client_socket = client_socket
        self.client_address = client_address

    def run(self):
        global data_size, fifo_01
        while True:
            self.start_time = time.perf_counter()
            self.buffer = self.client_socket.recv(data_size)
            print(len(self.buffer))
            mutex.lock()  # 加锁，防止其他线程同时访问
            fifo_01 += self.buffer
            mutex.unlock()  # 释放锁
            self.end_time = time.perf_counter()
            self.time_a = self.end_time - self.start_time
            print('thread_a_time:%s' % self.time_a)


class UnpackData(QThread):
    def __init__(self):
        super(UnpackData, self).__init__()
        self.buffer = b''  # 初始化接收缓冲区

    def run(self):
        global fifo_01
        while True:
            if len(fifo_01) >= 1000:
                mutex.lock()  # 加锁，防止其他线程同时访问
                self.buffer = fifo_01[0:999]
                fifo_01 = fifo_01[1000:]
                mutex.unlock()  # 释放锁
                self.start_time = time.perf_counter()
                unpack(self.buffer)
                self.end_time = time.perf_counter()
                time_b = self.end_time - self.start_time
                print('thread_b_time:%s' % time_b)
            elif 1000 > len(fifo_01) > 0:
                mutex.lock()  # 加锁，防止其他线程同时访问
                self.buffer = fifo_01[0:]
                fifo_01 = []
                mutex.unlock()  # 释放锁
                self.start_time = time.perf_counter()
                unpack(self.buffer)
                self.end_time = time.perf_counter()
                time_b = self.end_time - self.start_time
                print('thread_b_time:%s' % time_b)


class Window(QMainWindow, Ui_mainWindow, Chart):
    def __init__(self):
        super(Window, self).__init__()
        self.setupUi(self)
        self.host_name = None
        global ip, port
        # 存储地址
        self.dir = None
        self.save_path = None
        # 控件信号与槽连接
        # self.pushButton.released.connect(self.get_ip)
        self.pushButton_2.clicked.connect(self.file_choose)
        self.pushButton_3.released.connect(self.connecting)
        self.comboBox.activated[str].connect(self.chart_choose)
        # 设置view
        self.chart_list = [Chart() for i in range(8)]
        self.chart_view = QChartView(self.tableWidget)
        self.chart_view.setGeometry(QtCore.QRect(0, 0, 591, 431))
        self.chart_view.setChart(self.chart_list[0].chart)
        # 自动获取ip地址和port
        self.host_name = gethostname()
        ip = gethostbyname(self.host_name)
        port = 1234
        self.label.setText(ip)
        self.label_6.setText(str(port))
        # 创建服务器套接字
        self.sock = socket.socket(AF_INET, SOCK_STREAM)
        self.sock.bind((ip, port))
        self.sock.listen(10)

    def file_choose(self):
        self.dir = QtWidgets.QFileDialog.getExistingDirectory(None, "选取文件夹", ".")
        self.lineEdit_2.setText(self.dir)
        self.save_path = self.lineEdit_2.text()

    def chart_choose(self, chart_view_num):
        self.chart_view.setChart(self.chart_list[int(chart_view_num)].chart)

    def connecting(self):
        client_connect.start()
        client_connect.setPriority(QThread.HighPriority)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    client_threads = []  # 线程池
    unpack_threads = []  # 线程池
    window = Window()
    client_connect = ClientConnect()
    window.show()
    sys.exit(app.exec_())
