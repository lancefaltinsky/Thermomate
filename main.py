from wyze_sdk import Client
import configparser
import tkinter
import tkinter.ttk
from threading import Thread
from tkinter import font
import queue
from datetime import datetime
from PIL import ImageTk, Image

config = configparser.ConfigParser(interpolation=None)
config.read('config.ini')
if not config.has_section('wyze'):
    config['wyze'] = {}

cfg_changed = False
if not config.has_option('wyze', 'email'):
    config['wyze']['email'] = input('Please enter your Wyze email: ')
    cfg_changed = True

if not config.has_option('wyze','password'):
    config['wyze']['password'] = input('Please enter your Wyze password: ')
    cfg_changed = True

if cfg_changed:
    with open('config.ini', 'w') as cfg_file:
        config.write(cfg_file)

wyze_email = config['wyze']['email']
wyze_password = config['wyze']['password']


response = Client().login(email=wyze_email, password=wyze_password)
print("Connecting to Wyze client...")
client = Client(token=response['access_token'])

thermostats = client.thermostats.list()

class ThermoStatGui():
    def __init__(self) -> None:
        print("Initializing...")
        self.root = tkinter.Tk()
        self.fan_image = Image.open("./fan.png")
        self.fan_image = self.fan_image.resize((40, 40), Image.Resampling.LANCZOS)
        self.fan_icon = ImageTk.PhotoImage(self.fan_image)
        self.degree_symbol = '°'
        self.temperature_font = ('Roboto Thin', 120, 'normal')
        self.humidity_font = ('Roboto Cn', 12, 'normal')
        self.status_font = ('Roboto Light', 16, 'normal')
        self.root.minsize(300, 520)
        self.root.maxsize(300, 520)
        self.root.title("ThermoMate")
        self.elements_to_recolor_bg = []
        self.elements_to_recolor_fg = []
        # make sure we update the scalers the first run
        self.elements_to_recolor_bg.append(self.root)
        self.scaler_timeout = None

        self.heat_color = '#f5a742'
        self.cool_color = '#4287f5'
        self.off_color = 'grey'
        self.cur_color = self.off_color

        self.current_thermostat = client.thermostats.info(device_mac=thermostats[0].mac)
        self.thermostat_selection = tkinter.ttk.Combobox(self.root, values=[t.nickname for t in thermostats])
        self.thermostat_selection.current(0)
        self.thermostat_selection.bind("<<ComboboxSelected>>", self.select_thermostat)
        self.thermostat_selection.pack()
        self.elements_to_recolor_bg.append(self.thermostat_selection)
        self.fan_label = tkinter.Label(self.root, image=self.fan_icon)
        self.fan_label.pack(side=tkinter.TOP)
        self.elements_to_recolor_bg.append(self.fan_label)
        self.temp_label = tkinter.Label(self.root, text="-°", font=self.temperature_font, anchor=tkinter.CENTER)
        self.temp_label.pack(pady=(50, 0))
        self.temperature_queue = queue.Queue()

        self.humidity_label = tkinter.Label(self.root, text="-% humidity", font=self.humidity_font, anchor=tkinter.CENTER)
        self.humidity_label.pack(pady=(0, 5))

        self.status_label = tkinter.Label(self.root, text="Idle", font=self.status_font, anchor=tkinter.CENTER)
        self.status_label.pack(pady=(0, 15))
        self.elements_to_recolor_bg.append(self.status_label)

        self.elements_to_recolor_bg.append(self.temp_label)
        self.elements_to_recolor_bg.append(self.humidity_label)

        self.heating_frame = tkinter.Frame(self.root)
        self.heating_label = tkinter.Label(self.heating_frame, text='Heat to')
        self.heating_label.pack(side=tkinter.LEFT)
        self.elements_to_recolor_bg.append(self.heating_label)

        self.heating_scale = tkinter.Scale(self.heating_frame, from_=0, to=100, orient=tkinter.HORIZONTAL, length=200)
        self.heating_scale.pack(side=tkinter.RIGHT)
        self.heating_scale.bind("<ButtonRelease-1>", self.set_heating)
        self.heating_frame.pack()

        self.cooling_frame = tkinter.Frame(self.root)
        self.cooling_label = tkinter.Label(self.cooling_frame, text='Cool to')
        self.cooling_label.pack(side=tkinter.LEFT)
        self.elements_to_recolor_bg.append(self.heating_scale)
        self.cooling_scale = tkinter.Scale(self.cooling_frame, from_=0, to=100, orient=tkinter.HORIZONTAL, length=200)
        self.cooling_scale.bind("<ButtonRelease-1>", self.set_cooling)
        self.cooling_scale.pack(side=tkinter.RIGHT)
        self.cooling_frame.pack()
        self.elements_to_recolor_bg.append(self.cooling_label)
        self.elements_to_recolor_bg.append(self.cooling_scale)

        self.elements_to_recolor_bg.append(self.cooling_frame)
        self.elements_to_recolor_bg.append(self.heating_frame)

        self.current_cooling_point = None
        self.current_heating_point = None

        self.temperature_thread = Thread(target=self.temperature_check_tick, daemon=True)
        self.temperature_thread.start()

        self.root.after(1000, self.update_temperature)
        self.root.mainloop()

    def select_thermostat(self, event):
        print("Selecting thermostat")
        selected_index = self.thermostat_selection.current()
        self.current_thermostat = client.thermostats.info(device_mac=thermostats[selected_index].mac)
        print("Selected")

    def temperature_check_tick(self):
        while True:
            self.current_thermostat = client.thermostats.info(device_mac=self.current_thermostat.mac)
            thermostat_data = {
                'temp': round(float(self.current_thermostat.temperature)),
                'min_temp': round(float(self.current_thermostat.minimum_allowed_temperature)),
                'max_temp': round(float(self.current_thermostat.maximum_allowed_temperature)),
                'heating_point': self.current_thermostat.heating_setpoint,
                'cooling_point': self.current_thermostat.cooling_setpoint,
                'working_state': self.current_thermostat.working_state,
                'humidity': self.current_thermostat.humidity
            }
            self.temperature_queue.put(thermostat_data) 

    def update_temperature(self):
        if not self.temperature_queue.empty():
            thermostat_info = self.temperature_queue.get()
            self.temp_label.config(text=str(thermostat_info['temp']) + str(self.degree_symbol))
            self.humidity_label.config(text=f"{thermostat_info['humidity']}% humidity")
            delta = datetime.now() - self.scaler_timeout if self.scaler_timeout else None
            # ensure the temperature synchronizes but does not visually disrupt user experience
            if delta is None or delta.total_seconds() > 10:
                self.heating_scale.config(from_=thermostat_info["min_temp"], to=thermostat_info["max_temp"])
                self.heating_scale.set(int(thermostat_info["heating_point"]))
                self.cooling_scale.config(from_=thermostat_info["min_temp"], to=thermostat_info["max_temp"])
                self.cooling_scale.set(int(thermostat_info["cooling_point"]))
                self.scaler_timeout = datetime.now()

            self.status_label.config(text = thermostat_info['working_state'].capitalize())
            if thermostat_info['working_state'] == 'heating':
                self.cur_color = self.heat_color
            elif thermostat_info['working_state'] == 'cooling':
                self.cur_color = self.cool_color
            else:
                self.cur_color = self.off_color

            for e in self.elements_to_recolor_bg:
                e.configure(background=self.cur_color)

        self.root.after(1000, self.update_temperature)

    def set_cooling(self, v):
        client.thermostats.set_cooling_setpoint(device_mac=self.current_thermostat.mac,
                                               cooling_setpoint=self.cooling_scale.get(),
                                               device_model=self.current_thermostat.product.model)

    def set_heating(self, v):
        client.thermostats.set_heating_setpoint(device_mac=self.current_thermostat.mac,
                                               heating_setpoint=self.heating_scale.get(),
                                               device_model=self.current_thermostat.product.model)

ThermoStatGui()
