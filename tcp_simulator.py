import socket
import time
import random

def send_packet(sock, packet):
    sock.sendall((packet + '\n').encode('utf-8'))
    print(f"Sent: {packet}")

def random_frame():
    # Generate 32x24 = 768 random hex values (simulate thermal frame)
    return ' '.join(f"{random.randint(0,4095):04x}" for _ in range(32*24))

def main(host='127.0.0.1', port=9000):
    with socket.create_connection((host, port)) as sock:
        # Send serialno
        send_packet(sock, '#serialno:123456!')
        time.sleep(0.5)
        # Send frame
        frame = random_frame()
        send_packet(sock, f'#frame:{frame}!')
        time.sleep(0.5)
        # Send sensor
        adc1 = random.randint(200, 800)
        adc2 = random.randint(100, 500)
        mpy30 = random.choice([0, 1])
        send_packet(sock, f'#Sensor:ADC1={adc1},ADC2={adc2},MPY30={mpy30}!')
        time.sleep(0.5)
        # Repeat
        for i in range(5):
            frame = random_frame()
            send_packet(sock, f'#frame:{frame}!')
            adc1 = random.randint(200, 800)
            adc2 = random.randint(100, 500)
            mpy30 = random.choice([0, 1])
            send_packet(sock, f'#Sensor:ADC1={adc1},ADC2={adc2},MPY30={mpy30}!')
            time.sleep(1)

if __name__ == "__main__":
    main()
