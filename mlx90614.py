# Support for I2C based MLX90614 temperature sensors
#
# Copyright (C) 2025  Andrej Hapuzenkov <andrejhapuzenkov@gmail.com>, https://github.com/andrejhapuzenkov/mlx90614_for_klipper.git
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
from . import bus

MLX90614_CHIP_ADDR = 0x5A
MLX90614_I2C_SPEED = 100000

MLX90614_REGS = {
          'MLX90614_RAWIR1' : 0x04, # Raw data IR channel 1
          'MLX90614_RAWIR2' : 0x05, # Raw data IR channel 2
          'MLX90614_TA'     : 0x06, # Ambient temperature
          'MLX90614_TOBJ1'  : 0x07, # Object 1 temperature
          'MLX90614_TOBJ2'  : 0x08, # Object 2 temperature
          'MLX90614_TOMAX'  : 0x20, # Object temperature max register
          'MLX90614_TOMIN'  : 0x21, # Object temperature min register
          'MLX90614_PWMCTRL': 0x22, # PWM configuration register
          'MLX90614_TARANGE': 0x23, # Ambient temperature register
          'MLX90614_EMISS'  : 0x24, # Emissivity correction register
          'MLX90614_CONFIG' : 0x25, # Configuration register
          'MLX90614_ADDR'   : 0x2E, # Slave address register
          'MLX90614_ID1'    : 0x3C, # 1 ID register (read-only)
          'MLX90614_ID2'    : 0x3D, # 2 ID register (read-only)
          'MLX90614_ID3'    : 0x3E, # 3 ID register (read-only)
          'MLX90614_ID4'    : 0x3F  # 4 ID register (read-only)
    }
        
MLX90614_REPORT_TIME = .8
MLX90614_MIN_REPORT_TIME = .5

class MLX90614:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.name = config.get_name().split()[-1]
        self.reactor = self.printer.get_reactor()
        self.i2c = bus.MCU_I2C_from_config(config, MLX90614_CHIP_ADDR,
                                           MLX90614_I2C_SPEED)
        self.mcu = self.i2c.get_mcu()
        self.report_time = config.getfloat('MLX90614_report_time', MLX90614_REPORT_TIME,
                                           minval=MLX90614_MIN_REPORT_TIME)
        self.temp = self.min_temp = self.max_temp = 0.0
        self.sample_timer = self.reactor.register_timer(self._sample_mlx90614)
        self.printer.add_object("MLX90614 " + self.name, self)
        self.printer.register_event_handler("klippy:connect",
                                            self.handle_connect)

    def handle_connect(self):
        self._init_mlx90614()
        self.reactor.update_timer(self.sample_timer, self.reactor.NOW)

    def setup_minmax(self, min_temp, max_temp):
        self.min_temp = min_temp
        self.max_temp = max_temp

    def setup_callback(self, cb):
        self._callback = cb

    def get_report_time_delta(self):
        return self.report_time

    def _init_mlx90614(self):
        # Check and report the chip ID but ignore errors since many
        # chips don't have it
        try:
            prodid = self.read_register('MLX90614_ID1', 1)[0]
            logging.info("mlx90614: Chip ID %#x" % prodid)
        except:
            pass

    def _sample_mlx90614(self, eventtime):
        try:
            sample = self.read_register('MLX90614_TOBJ1', 2)
            self.temp = self.degrees_from_sample(sample)
        except Exception:
            logging.exception("mlx90614: Error reading data")
            self.temp = 0.0
            return self.reactor.NEVER

        if self.temp < self.min_temp or self.temp > self.max_temp:
            self.printer.invoke_shutdown(
                "MLX90614 temperature %0.1f outside range of %0.1f:%.01f"
                % (self.temp, self.min_temp, self.max_temp))

        measured_time = self.reactor.monotonic()
        self._callback(self.mcu.estimated_print_time(measured_time), self.temp)
        return measured_time + self.report_time

    def degrees_from_sample(self, x):
        return (x * 0.02) - 273.15

    def read_register(self, reg_name, read_len):
        # read a single register
        regs = [MLX90614_REGS[reg_name]]
        params = self.i2c.i2c_read(regs, read_len)
        return bytearray(params['response'])

    def write_register(self, reg_name, data):
        if type(data) is not list:
            data = [data]
        reg = MLX90614_REGS[reg_name]
        data.insert(0, reg)
        self.i2c.i2c_write(data)

    def get_status(self, eventtime):
        return {
            'temperature': round(self.temp, 2),
        }
    

def load_config(config):
    # Register sensor
    pheaters = config.get_printer().load_object(config, "heaters")
    pheaters.add_sensor_factory("MLX90614", MLX90614)
