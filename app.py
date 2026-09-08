from flask import Flask, jsonify 
ECHO is on.
app = Flask(__name__) 
ECHO is on.
@app.route('/health', methods=['GET']) 
def health_check(): 
    return jsonify({ 
        'status': 'healthy', 
        'message': 'Customer Management System is running' 
    }) 
ECHO is on.
if __name__ == '__main__': 
    app.run(debug=True, host='0.0.0.0', port=5000) 
