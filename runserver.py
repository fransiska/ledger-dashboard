#!/bin/env python
from ledgerdashboard import app
from ledgerdashboard import settings

app.run(host="0.0.0.0", debug=True, port=settings.PORT)
