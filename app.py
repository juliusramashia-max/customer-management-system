from flask import Flask, jsonify
from config import Config
from database import init_db
from auth import auth_bp
from customers import customers_bp
from products import products_bp
from invoices import invoices_bp
from payments import payments_bp
from credit_notes import credit_notes_bp

app = Flask(__name__)
app.config.from_object(Config)

init_db(app)

app.register_blueprint(auth_bp)
app.register_blueprint(customers_bp)
app.register_blueprint(products_bp)
app.register_blueprint(invoices_bp)
app.register_blueprint(payments_bp)
app.register_blueprint(credit_notes_bp)


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'message': 'Customer Management System is running'
    })


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)