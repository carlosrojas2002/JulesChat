import boto3
import argparse
import os
import logging
import requests
import time

# Configuración de logs
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())

def get_zip_file_path(input_path):
    candidate = os.path.join(input_path, 'lex_zip_package', 'lex-import.zip')
    if os.path.exists(candidate): return candidate
    candidate = os.path.join(input_path, 'lex-import.zip')
    if os.path.exists(candidate): return candidate
    for root, dirs, files in os.walk(input_path):
        for file in files:
            if file.endswith(".zip"): return os.path.join(root, file)
    return None

def start_lex_import(bot_id, bot_locale_id, region, zip_file_path):
    client = boto3.client('lexv2-models', region_name=region)

    # PASO 0: Obtener detalles del bot REAL
    logger.info(f"0. Obteniendo metadatos del bot {bot_id}...")
    try:
        bot_details = client.describe_bot(botId=bot_id)
        bot_name = bot_details['botName']
        bot_role_arn = bot_details['roleArn']
        data_privacy = bot_details['dataPrivacy']
        idle_ttl = bot_details['idleSessionTTLInSeconds']
        logger.info(f"   Bot detectado: {bot_name}")
    except Exception as e:
        logger.error(f"Error obteniendo detalles del bot: {e}")
        raise e

    # PASO 1: URL de Carga
    logger.info("1. Solicitando URL de carga...")
    try:
        response = client.create_upload_url()
        import_id = response['importId']
        upload_url = response['uploadUrl']
        logger.info(f"   Import ID: {import_id}")
    except Exception as e:
        logger.error(f"Error create_upload_url: {e}")
        raise e

    # PASO 2: Subir ZIP
    logger.info(f"2. Subiendo archivo ZIP...")
    try:
        with open(zip_file_path, 'rb') as f:
            headers = {'Content-Type': 'application/zip'}
            res = requests.put(upload_url, data=f, headers=headers)
            if res.status_code not in [200, 201, 202]:
                raise Exception(f"Status: {res.status_code}, Msg: {res.text}")
        logger.info("   Subida exitosa.")
    except Exception as e:
        logger.error(f"Error subiendo ZIP: {e}")
        raise e

    # PASO 3: Iniciar Importación
    logger.info("3. Iniciando importación en Lex...")
    try:
        response = client.start_import(
            importId=import_id,
            resourceSpecification={
                'botImportSpecification': {
                    'botName': bot_name,        # Usamos el nombre real
                    'roleArn': bot_role_arn,
                    'dataPrivacy': data_privacy,
                    'idleSessionTTLInSeconds': idle_ttl
                }
            },
            mergeStrategy='Overwrite' # IMPORTANTE: Overwrite para actualizar
        )
        logger.info(f"   Estado inicial: {response['importStatus']}")
        return import_id
    except Exception as e:
        logger.error(f"Error start_import: {e}")
        raise e

def wait_for_import(import_id, region):
    client = boto3.client('lexv2-models', region_name=region)
    logger.info(f"4. Esperando finalización del Job {import_id}...")

    while True:
        try:
            # Hacemos la llamada a la API
            response = client.describe_import(importId=import_id)
            status = response['importStatus']
            logger.info(f"   Estado actual: {status}")

            # Verificamos estado SIN lanzar excepción dentro del try
            if status == 'Completed':
                logger.info("   ¡Importación COMPLETADA!")
                break

            if status in ['Failed', 'Deleted']:
                failures = response.get('failureReasons', [])
                # Esto romperá el bucle porque raise saldrá de la función
                logger.error(f"IMPORTACIÓN FALLIDA: {failures}")
                raise Exception(f"Fallo Lex: {failures}")

            time.sleep(5)

        except Exception as e:
            # Si el error es el que acabamos de lanzar (Fallo Lex), lo re-lanzamos para que el script falle y pare.
            if "Fallo Lex" in str(e):
                raise e

            # Si es otro error (de red, boto3), esperamos y reintentamos
            logger.warning(f"Error temporal de conexión (reintentando...): {e}")
            time.sleep(5)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bot-id', type=str, required=True)
    parser.add_argument('--bot-locale-id', type=str, required=True)
    parser.add_argument('--aws-region', type=str, required=True)
    parser.add_argument('--input-path', type=str, required=True)
    args = parser.parse_args()

    zip_path = get_zip_file_path(args.input_path)
    if not zip_path:
        raise FileNotFoundError("No se encontró el ZIP")

    import_id = start_lex_import(args.bot_id, args.bot_locale_id, args.aws_region, zip_path)
    wait_for_import(import_id, args.aws_region)

if __name__ == '__main__':
    main()