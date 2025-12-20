"""
MQ-135 Gas Sensor calculations for air quality monitoring.
Converts ADC readings to gas concentration (PPM).
"""
import math

class MQ135GasSensor:
    def __init__(self, rl=10.0, v_in=5.0, adc_resolution=1024):
        """
        Initialize MQ-135 gas sensor parameters.
        
        Args:
            rl: Load resistance in kΩ (typically 10kΩ)
            v_in: Input voltage (typically 5V)
            adc_resolution: ADC resolution (10-bit = 1024, 12-bit = 4096)
        """
        self.rl = rl
        self.v_in = v_in
        self.adc_resolution = adc_resolution
        
        # R0 is the sensor resistance in clean air (needs calibration)
        # Default value - should be calibrated for each sensor
        self.r0 = 76.63  # Typical value, MUST be calibrated
        
        # Curve fitting parameters for different gases
        # Format: {gas: (a, b)} where PPM = a * (Rs/R0)^b
        self.gas_curves = {
            'CO2': (116.6020682, -2.769034857),      # Carbon Dioxide
            'CO': (605.18, -3.937),                    # Carbon Monoxide
            'NH3': (102.2, -2.473),                    # Ammonia
            'Alcohol': (77.255, -3.18),                # Alcohol
            'Acetone': (34.668, -3.369),               # Acetone
            'Toluene': (44.947, -3.445),               # Toluene
        }
    
    def set_r0(self, r0):
        """Set the R0 calibration value (sensor resistance in clean air)."""
        self.r0 = r0
    
    def set_calibration(self, r0=None, rl=None, vcc=None):
        """
        Set calibration parameters for the gas sensor.
        
        Args:
            r0: Sensor resistance in clean air (kΩ)
            rl: Load resistance (kΩ)
            vcc: Supply voltage (V)
        """
        if r0 is not None:
            self.r0 = r0
        if rl is not None:
            self.rl = rl
        if vcc is not None:
            self.v_in = vcc
        print(f"Gas sensor calibration updated: R0={self.r0:.2f}kΩ, RL={self.rl}kΩ, VCC={self.v_in}V")
    
    def calibrate_r0(self, adc_value, clean_air_factor=3.6):
        """
        Calibrate R0 value using clean air measurement.
        
        Args:
            adc_value: ADC reading in clean air
            clean_air_factor: Rs/R0 ratio in clean air (typically 3.6 for MQ-135)
        
        Returns:
            Calculated R0 value
        """
        rs = self.calculate_rs(adc_value)
        r0 = rs / clean_air_factor
        self.r0 = r0
        return r0
    
    def calculate_rs(self, adc_value):
        """
        Calculate sensor resistance from ADC reading.
        
        Rs = [(Vin * RL) / Vout] - RL
        where Vout = (ADC / ADC_MAX) * Vin
        
        Args:
            adc_value: Raw ADC reading (0-1023 for 10-bit, 0-4095 for 12-bit)
        
        Returns:
            Sensor resistance Rs in kΩ
        """
        if adc_value == 0:
            return float('inf')
        
        v_out = (adc_value / self.adc_resolution) * self.v_in
        if v_out == 0:
            return float('inf')
        
        rs = ((self.v_in * self.rl) / v_out) - self.rl
        return max(rs, 0.1)  # Prevent negative or zero values
    
    def get_ppm(self, adc_value, gas='CO2'):
        """
        Convert ADC reading to gas concentration in PPM.
        
        Args:
            adc_value: Raw ADC reading
            gas: Target gas type (CO2, CO, NH3, Alcohol, Acetone, Toluene)
        
        Returns:
            Gas concentration in PPM
        """
        if gas not in self.gas_curves:
            raise ValueError(f"Unknown gas type: {gas}. Supported: {list(self.gas_curves.keys())}")
        
        rs = self.calculate_rs(adc_value)
        ratio = rs / self.r0
        
        a, b = self.gas_curves[gas]
        ppm = a * math.pow(ratio, b)
        
        return max(ppm, 0)  # Prevent negative values
    
    def get_air_quality_index(self, adc_value):
        """
        Get simplified air quality index.
        
        Returns:
            Tuple of (index, description, level)
            - index: 0-5 (0=excellent, 5=hazardous)
            - description: Text description
            - level: CO2 PPM estimate
        """
        co2_ppm = self.get_ppm(adc_value, 'CO2')
        
        if co2_ppm < 400:
            return (0, 'Excellent', co2_ppm)
        elif co2_ppm < 600:
            return (1, 'Good', co2_ppm)
        elif co2_ppm < 1000:
            return (2, 'Moderate', co2_ppm)
        elif co2_ppm < 1500:
            return (3, 'Poor', co2_ppm)
        elif co2_ppm < 2000:
            return (4, 'Unhealthy', co2_ppm)
        else:
            return (5, 'Hazardous', co2_ppm)
    
    def __repr__(self):
        return f"MQ135(R0={self.r0:.2f}kΩ, RL={self.rl}kΩ, Vin={self.v_in}V)"


if __name__ == "__main__":
    # Example usage
    sensor = MQ135GasSensor()
    
    print("MQ-135 Gas Sensor Calculator")
    print(f"Configuration: {sensor}")
    print("\nCalibration in clean air (ADC=400):")
    r0 = sensor.calibrate_r0(400)
    print(f"Calculated R0: {r0:.2f} kΩ")
    
    print("\nExample readings:")
    test_values = [300, 500, 800, 1200, 2000]
    for adc in test_values:
        rs = sensor.calculate_rs(adc)
        ratio = rs / sensor.r0
        co2 = sensor.get_ppm(adc, 'CO2')
        index, desc, _ = sensor.get_air_quality_index(adc)
        print(f"ADC={adc:4d} -> Rs={rs:6.2f}kΩ, Rs/R0={ratio:.3f}, CO2={co2:7.1f}ppm, AQI={desc}")
