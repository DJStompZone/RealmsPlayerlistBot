from threading import Thread
from flask import Flask
from base64 import urlsafe_b64decode as d64

app = Flask("app")
# Flask App Rick
assembled_page = d64(b"".join( [
  b"PGh0bWw-CiAgPGhlYWQ-CiAgICA8L2hlYWQ-CiAgICA8Ym9keT4KICAgICAgCiAgICAgIDxzcGFuIHN0eWxlID0icG9zaXRpb246YWJzb2x1dGU7bWluLXdpZHRoOjEwMHZ3O21heC1oZWlnaHQ6",
  b"NzV2aDthbGlnbi1pdGVtczpjZW50ZXI7Ij4KICAgICAgPGRpdiBzdHlsZT0icG9zaXRpb246cmVsYXRpdmU7dmVydGljYWwtYWxpZ246Y2VudGVyO21pbi13aWR0aDo1MHZoO21pbi1oZWlnaHQ6",
  b"MTBlbTt0ZXh0LWFsaWduOmNlbnRlcjsiPgogICAgICA8cD5JJ20gYSB3ZWJwYWdlLCBNb3J0eSE8YnI-CiAgICAgICAgSSB0dXJuZWQgbXlzZWxmIGludG8gYSB3ZWJwYWdlITxicj4KCiAgICAg",
  b"IDxpbWcgc3R5bGU9InBvc2l0aW9uOnJlbGF0aXZlO21hcmdpbjoydmg7bWluLWhlaWdodDo1dmg7bWF4LWhlaWdodDo1MHZoO3dpZHRoOmF1dG8iIHNyYz0naHR0cHM6Ly9pLmltZ3VyLmNvbS9H",
  b"U29yVmN3LnBuZyc-PC9pbWc-CiAgICAgIDxicj5JJ20gRmxhc2sgQXBwIFJpY2shITwvcD4KICAgIDwvZGl2PgogICAgPC9zcGFuPgogICAgPC9kaXY-CiAgICA8L2JvZHk-CiAgICA8L2h0bWw-"]))

@app.route('/')
def home():
  return assembled_page

def run():
    app.run(host="0.0.0.0", port=8080)


def keep_alive():
    server = Thread(target=run)
    server.start()

if __name__ == "__main__":
    keep_alive() 
