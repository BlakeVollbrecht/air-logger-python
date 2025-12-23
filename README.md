# Air Logger


## Description

Logs air metrics such as temperature, humidity, and CO2 levels. Reads data from sensors connected to a Raspberry Pi and stores as time series data in a local MySQL (MariaDB) database. Also hosts Grafana to make charts of this data accessible on local network.

This uses python due to the available packages for interfacing with the sensors. It involves setup on a raspberry pi over ssh rather than applying a premade image.

### Intended Hardware

- Raspberry Pi Zero W (wifi) with Raspberry Pi OS Lite (headless)
- Adafruit BME688 temp/humidity/pressure/voc module
- Senseair Sunrise 006-0-0008 CO2 sensor


## How to use

### Connect sensors

- Senseair Sunrise 006-0-0008 connections:
    - Pin 1 (GND) → Raspberry Pi GPIO GND
    - Pin 2 (VBB) → Raspberry Pi GPIO 3.3V
    - Pin 3 (VDDIO) → Raspberry Pi GPIO 3.3V
    - Pin 4 (SDA) → Raspberry Pi GPIO SDA (pin 3)
    - Pin 5 (SCL) → Raspberry Pi GPIO SCL (pin 5)
    - Pin 6 (COMSEL) → Raspberry Pi GPIO GND (low is i2c, high is uart/modbus)
    - Pin 7 (nRDY) → no connection
    - Pin 8 (DVCC) → no connection
    - Pin 9 (EN) → Raspberry Pi GPIO 3.3V (hardwiring causes it to take a reading every 16 seconds, could connect to i/o pin and enable it less frequently with code)
- Adafruit BME688 connections:
    - Pin 1 (VIN) → Raspberry Pi GPIO 3.3V
    - Pin 2 (3Vo) → no connection
    - Pin 3 (GND) → Raspberry Pi GPIO GND
    - Pin 4 (SCK) → Raspberry Pi GPIO SCL (pin 5)
    - Pin 5 (SDO) → no connection
    - Pin 6 (SDI) → Raspberry Pi GPIO SDA (pin 3)
    - Pin 7 (CS) → no connection
- may need pull-up resistors to 3.3V on the SDA and SDL lines if not connecting sensor modules with strong enough internal ones (something like 10kΩ. could go 4.7kΩ ) 
    - Adafruit BME688 supposedly has 10kΩ pull-up on SCK and SDI, so if it's connected altogether with other sensors, it will pull-up the lines for everything.
    - Sensair Sunrise apparently has a weaker (100kΩ) internal pull-up on the SCL pin, and none on the SDA pin, so some external pull-up is needed for this sensor by itself.

### Configure on Raspberry Pi Zero W

- gotchas connecting to raspberry pi
    - Raspberry Pi Imager may set username to the installing machine username instead of default "pi" (happens when enabling ssh?)
    - Ghostty terminal on macOS requires a security setting to be disabled or it just won't ssh/ping the raspberry pi inexplicably (System Settings > Privacy & Security > Local Network > Ghostty (or other terminal) > Enable)
    - Ghostty terminal on macOS sets the $TERM variable on the raspberry pi to ```xterm-ghostty``` when connecting via ssh, which causes things like ```top``` not to work due to graphics dependencies; can fix by manually setting $TERM when connecting: ```TERM=xterm-256color ssh pi@<ip address>```

- configure graceful shutdown button (optional)
    - connect GND to the raspberry pi GPIO pin 24 (or others) through a momentary switch/button
    - edit /boot/firmware/config.txt
    - add `dtoverlay=gpio-shutdown,gpio_pin=24` to the end of the file in the `[all]` section (apply to all raspberry pi models)
    - save the config file and `sudo reboot` to apply changes

- update system:
    - `sudo apt update`

- enable I2C:
    - `sudo raspi-config`
    - navigate to Interface Options > I2C > Enable
    - `sudo reboot`

- install I2C tools:
    - `sudo apt install i2c-tools python3-smbus`
    - verify bus with `i2cdetect -y 1` (should show addresses 0x77 for Adafruit module and 0x68 for Sunrise if they're connected properly)

- make directory ~/logger (could use a directory other than /home/pi/logger but some of the steps here will need that different path)
    - change to this directory and create/copy air_logger.py into it

- install python program dependencies:
    - `sudo apt install python3-pip`
    - `python3 -m venv sensor_env` (may have needed something like `sudo apt install python3-venv libgpiod2` first)
    - `source sensor_env/bin/activate` to go into a python virtual environment for pip dependencies
    - `pip install --upgrade pip`
    - `pip install adafruit-circuitpython-bme680 adafruit-blinka` for Adafruit BME688
    - `pip install smbus2` for Sensair Sunrise
    - `pip install mysql-connector-python`
    - `pip list` to verify packages are installed

- install & configure db:
    - `sudo apt install mariadb-server -y`
    - `sudo mysql_secure_installation` -> set root password, remove anonymous users and testing items
    - run MySQL shell to create database and table `sudo mysql -u root -p`
        ```
        CREATE DATABASE airmetrics;
        USE airmetrics;
        CREATE TABLE readings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            timestamp DATETIME NOT NULL,
            co2_ppm FLOAT,
            temperature_c FLOAT,
            humidity_pct FLOAT,
            pressure_hpa FLOAT,
            gas_ohms FLOAT
        );
        CREATE USER 'grafana'@'localhost' IDENTIFIED BY 'strongpassword';
        GRANT SELECT ON airmetrics.* TO 'grafana'@'localhost';
        GRANT INSERT ON airmetrics.* TO 'grafana'@'localhost';
        FLUSH PRIVILEGES;
        ```
- install & configure Grafana:
    - install prerequisites: `sudo apt-get install -y apt-transport-https software-properties-common wget`
    - add GPG key to verify Grafana packages:
        - `sudo mkdir -p /etc/apt/keyrings/`
        - `wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor | sudo tee /etc/apt/keyrings/grafana.gpg > /dev/null`
        - `echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | sudo tee /etc/apt/sources.list.d/grafana.list`
    - `sudo apt-get update`
    - `sudo apt-get install grafana`
    - set binding:
        - edit `/etc/grafana/grafana.ini` with elevated permissions (i.e. sudo)
        - under `[server]` set `http_addr = 0.0.0.0` (default is blank which is localhost only (internal to raspberry pi))
    - modify service to be resilient to failures:
        - ```sudo systemctl edit grafana-server```
          - add lines in editable section near top and save/exit:
            - ```[Service]```
            - ```Restart=always```
            - ```RestartSec=10```
    - start and enable Grafana:
        - `sudo systemctl daemon-reload`
        - `sudo systemctl start grafana-server`
        - `sudo systemctl enable grafana-server`
        - check status: `sudo systemctl status grafana-server`
    - access Grafana:
        - http://*(pi's ip address)*:3000
        - default login: username = admin, password = admin
        - *I couldn't consistently access it in chrome or firefox, but it works in safari*
    - add data source in Grafana:
        - Connections (on left sidebar) > Data sources > Add data source > MySQL
        - configure the following for the data source:
            - host url: `localhost:3306`
            - database name, username, password: matching the database connection config in the code
            - TLS client auth: disabled
            - timezone: leave blank? can set to "browser"?
            - Min time interval: match interval that data is saved by code
    - create a dashboard for the datasource in Grafana:
        - add a visualization for each metric with a query similar to the following:
            - SELECT $__timeGroupAlias(timestamp, $__interval), AVG(temperature_c) AS temperature_c
              FROM readings
              WHERE $__timeFilter(timestamp)
              GROUP BY 1
              ORDER BY 1
            - also do visualization/query for temperature_c, humidity_pct, pressure_hpa, gas_ohms


- to manually run program (optional):
    - need to ensure it's in the virtual environment with the dependencies before running the code: `source sensor_env/bin/activate`
    - `python3 main.py` (whatever the main entry of the program is)

- configure program to start whenever system starts:
    - create a file (systemd service) `/etc/systemd/system/airlogger.service` containing the following:
        ```
        [Unit]
        Description=Air Logger
        After=network.target

        [Service]
        User=pi
        WorkingDirectory=/home/pi/logger
        ExecStart=/home/pi/logger/sensor_env/bin/python3 /home/pi/logger/air_logger.py
        Restart=always
        StandardOutput=journal
        StandardError=journal

        [Install]
        WantedBy=multi-user.target
        ```
    - `sudo systemctl enable airlogger.service && sudo systemctl start airlogger.service`
