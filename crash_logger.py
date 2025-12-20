"""
Crash logger for EmberEye - logs uncaught exceptions to file for debugging
"""
import sys
import traceback
import os
from datetime import datetime

def setup_crash_logger():
    """Setup global exception handler to log crashes to file"""
    crash_log_path = os.path.join(os.path.dirname(__file__), 'logs', 'crash.log')
    
    # Ensure logs directory exists
    os.makedirs(os.path.dirname(crash_log_path), exist_ok=True)
    
    def exception_handler(exc_type, exc_value, exc_traceback):
        """Log uncaught exceptions to crash.log"""
        if issubclass(exc_type, KeyboardInterrupt):
            # Don't log keyboard interrupts
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        # Log to file
        try:
            with open(crash_log_path, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"Crash at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"{'='*80}\n")
                traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
                f.write(f"\n")
        except Exception as e:
            print(f"Failed to write crash log: {e}")
        
        # Also print to console
        print(f"\nFATAL ERROR - Check {crash_log_path} for details")
        traceback.print_exception(exc_type, exc_value, exc_traceback)
    
    # Install the exception handler
    sys.excepthook = exception_handler
    print(f"Crash logger initialized: {crash_log_path}")
