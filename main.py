from flask import Flask, redirect, request
import requests
from lxml import etree

from routes.saml import saml_bp

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Use a secure key in production
app.register_blueprint(saml_bp)

# CAS config
CAS_LOGIN_URL = "https://weblogin.asu.edu/cas/login"
CAS_VALIDATE_URL = "https://weblogin.asu.edu/cas/serviceValidate"
SERVICE_URL = "https://verify.devil2devil.asu.edu/auth/cas/callback"  # This must match your route and be registered with CAS

@app.route('/')
def hello_world():
    return 'Hello, World!'

@app.route('/health')
def health():
    return {'status': 'healthy'}


@app.route('/auth/cas')
def cas_login():
    redirect_url = f"{CAS_LOGIN_URL}?service={SERVICE_URL}"
    return redirect(redirect_url)

@app.route('/auth/cas/callback')
def cas_callback():
    ticket = request.args.get('ticket')
    if not ticket:
        return "Missing CAS ticket", 400

    validate_url = f"{CAS_VALIDATE_URL}?ticket={ticket}&service={SERVICE_URL}"
    res = requests.get(validate_url)

    if res.status_code != 200:
        return "CAS validation failed", 500

    try:
        root = etree.fromstring(res.content)
        ns = {'cas': 'http://www.yale.edu/tp/cas'}

        success = root.find('cas:authenticationSuccess', ns)
        if success is None:
            return "CAS authentication failed", 401

        netid = success.find('cas:user', ns).text
        attributes = success.find('cas:attributes', ns)

        user_info = {
            'netid': netid
        }

        if attributes is not None:
            for element in attributes:
                tag = etree.QName(element).localname
                user_info[tag] = element.text

        return user_info
    except Exception as e:
        return f"Error parsing CAS response: {str(e)}", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
