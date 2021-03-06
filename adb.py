import cv2
import numpy as np
import logging
import time

from ppadb.client import Client as AdbClient
import config

class Adb():
    def __init__(self):
        client = AdbClient(host="127.0.0.1", port=5037)
        devices = client.devices()
        if len(devices) == 0:
            raise Exception('There is no ADB devices')

        self.device = devices[0]
        self.app_name = 'com.firsttouchgames.smp'

    def get_screen(self, color: bool = True):
        dim = config.screen_size

        for idx in range(10):
            buffer = np.frombuffer(self.device.screencap(), dtype='uint8')

            if color:
                img = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
            else:
                img = cv2.imdecode(buffer, cv2.IMREAD_GRAYSCALE)
 
            if dim == list(img.shape[0:2]):
                break

            logging.warning('Score! Match app is not active. Trying to run the app')
            self.start_app()
            time.sleep(5)
       
        return img

    def touch(self, x, y):
        self.device.input_tap(x, y)
        
    def swipe(self, start_x, start_y, end_x, end_y, duration):
        self.device.input_swipe(start_x, start_y, end_x, end_y, duration)

    def start_app(self):
        self.device.shell(f'monkey -p {self.app_name} -c android.intent.category.LAUNCHER 1')
        
    def stop_app(self):
        self.device.shell(f'am force-stop {self.app_name}')
        
    def restart_app(self):
        self.stop_app()
        time.sleep(5)
        self.start_app()
        time.sleep(5)