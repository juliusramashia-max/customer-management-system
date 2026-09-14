from flask import Flask, jsonify
from config import Config
from database import init_db
from auth import auth_bp
from customers import customers_bp   # NEW

app = Flask(__name__)
app.config.from_object(Config)

init_db(app)

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(customers_bp)   # NEW


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'message': 'Customer Management System is running'
    })


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)