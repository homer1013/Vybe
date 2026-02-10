# Serial Monitor / Non-UTF8 Output

```bash
vybe run --tag serial arduino-cli monitor -p /dev/ttyUSB0 -c baudrate=115200
vybe s --redact
vybe share --redact --errors
```

Vybe replaces invalid UTF-8 bytes instead of crashing, so raw serial data can still be captured.
