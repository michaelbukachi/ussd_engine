### Instructions

1. Install the dependencies in `requirements.txt`
2. Run `python example.py`
3. Access the web app on http://127.0.0.1:5000/ussd/
```json
{
  "phoneNumber": "254711111111",
  "sessionId": "10000",
  "text": "1",
  "serviceCode": "856"
}
```
The `text` field is for user input

In order to reset the session, change the value of `sessionId`