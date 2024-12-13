import json
import boto3
import base64
from datetime import datetime
from collections import defaultdict

# Cliente de S3
s3 = boto3.client('s3')

# Nombre del bucket S3
S3_BUCKET_NAME = "fraud-detection-resultsss"

# Historial de transacciones (en memoria para pruebas en tiempo real)
transaction_history = defaultdict(list)

def is_fraudulent(transaction):
    """
    Lógica básica para identificar transacciones fraudulentas.
    """
    # Caso 1: Monto mayor a 10,000 USD
    if transaction.get("amount", 0) > 10000:
        return "High Value"

    # Caso 2: Más de 3 transacciones con la misma cuenta en un tiempo cercano (1 minuto)
    account_id = transaction.get("account_id")
    timestamp = datetime.strptime(transaction.get("timestamp"), "%Y-%m-%dT%H:%M:%SZ")
    transaction_history[account_id].append(timestamp)
    recent_transactions = [t for t in transaction_history[account_id] if (timestamp - t).total_seconds() <= 60]
    if len(recent_transactions) > 3:
        return "Too Many Transactions"

    # Caso 3: Transacción en un país diferente al de origen de la tarjeta
    origin_country = transaction.get("origin_country")
    destination_country = transaction.get("destination_country")
    if origin_country and destination_country and origin_country != destination_country:
        return "Cross-Border Transaction"

    # Caso 4: Intentos seguidos de transacciones altas en cuentas con saldo bajo
    balance = transaction.get("balance", 0)
    if transaction.get("amount", 0) > balance * 0.9:
        return "High Value with Low Balance"

    return "LEGIT"

def lambda_handler(event, context):
    """
    Función principal de Lambda para procesar eventos de Kinesis.
    """
    # Lista para almacenar registros procesados
    processed_records = []
    fraud_records = []  # Lista de fraudes detectados

    for record in event['Records']:
        # Decodifica los datos Base64 del evento de Kinesis
        decoded_data = base64.b64decode(record['kinesis']['data']).decode('utf-8')
        
        # Convierte el string JSON en un diccionario Python
        payload = json.loads(decoded_data)

        # Determina el estado de la transacción
        fraud_status = is_fraudulent(payload)
        payload["fraud_status"] = fraud_status
        payload["processed_at"] = datetime.utcnow().isoformat()

        # Agrega el registro procesado a la lista
        processed_records.append(payload)

        # Si es un fraude, agregarlo a la lista de fraudes
        if fraud_status != "LEGIT":
            fraud_records.append(payload)

    # Guarda los resultados en un archivo JSON en S3
    file_name = f"fraud_results_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.json"
    s3.put_object(
        Bucket=S3_BUCKET_NAME,
        Key=file_name,
        Body=json.dumps({
            "total_records": len(processed_records),
            "fraud_count": len(fraud_records),
            "fraud_details": fraud_records
        })
    )

    return {
        'statusCode': 200,
        'body': json.dumps(f"Processed {len(processed_records)} records. Detected {len(fraud_records)} frauds.")
    }