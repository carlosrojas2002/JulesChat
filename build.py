import argparse
import os
import json
import zipfile
import logging
import csv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def create_lex_structure(utterances, locale_id, bot_name, bot_id, bot_role_arn):
    """
    Crea los diccionarios JSON con la sintaxis EXACTA de Lex V2.
    """
    intent_name = "NuevasFrasesImportadas"

    # 1. Intent.json
    intent_json = {
        "name": intent_name,
        "description": "Importado via SageMaker",
        "parentIntentSignature": None,
        "sampleUtterances": [{"utterance": u} for u in utterances],
        "intentConfirmationSetting": None,
        "intentClosingSetting": None,
        "inputContexts": None,
        "outputContexts": None,
        "kendraConfiguration": None,
        "dialogCodeHook": None,
        "fulfillmentCodeHook": None,
        "slotPriorities": []
    }

    # 2. BotLocale.json
    bot_locale_json = {
        "localeId": locale_id,
        "nluConfidenceThreshold": 0.40,
        "voiceSettings": {
            "voiceId": "Lupe",
            "engine": "standard"
        }
    }

    # 3. Bot.json (CORREGIDO)
    bot_json = {
        "name": bot_name,
        "identifier": bot_id,
        "roleArn": bot_role_arn,
        "dataPrivacy": {"childDirected": False},
        # CORRECCIÓN DE MAYÚSCULAS AQUÍ (TTL debe ser mayúscula)
        "idleSessionTTLInSeconds": 300,
        "botTags": {},
        "testBotAliasTags": {}
    }

    # 4. Manifest.json (CORREGIDO)
    # Faltaba el resourceType, vital para que Lex sepa qué está leyendo
    manifest_json = {
        "metaData": {
            "schemaVersion": "1.0",
            "resourceType": "BOT",  # <--- ESTO FALTABA
            "importType": "LEX",
            "importStatus": "IN_PROGRESS"
        }
    }

    return intent_name, intent_json, bot_locale_json, bot_json, manifest_json

def create_lex_import_zip(input_csv_path, output_zip_path, bot_locale_id, bot_name, bot_id, bot_role_arn):
    utterances = []
    try:
        with open(input_csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if row:
                    if row[0].lower() in ['transcript', 'utterance', 'phrase', 'frase']: continue
                    utterances.append(row[0])
    except Exception as e:
        logging.warning(f"CSV vacío o error: {e}")

    # Generar JSONs
    intent_name, intent_json, bot_locale_json, bot_json, manifest_json = create_lex_structure(utterances, bot_locale_id, bot_name, bot_id, bot_role_arn)

    logging.info(f"Empaquetando bot: {bot_name} / ID: {bot_id}")

    with zipfile.ZipFile(output_zip_path, 'w') as zipf:
        zipf.writestr("Manifest.json", json.dumps(manifest_json, indent=4))

        base_bot = "Bot"
        base_locale = f"{base_bot}/BotLocales/{bot_locale_id}"
        base_intent = f"{base_locale}/Intents/{intent_name}"

        zipf.writestr(f"{base_bot}/Bot.json", json.dumps(bot_json, indent=4))
        zipf.writestr(f"{base_locale}/BotLocale.json", json.dumps(bot_locale_json, indent=4))
        zipf.writestr(f"{base_intent}/Intent.json", json.dumps(intent_json, indent=4))

    logging.info("ZIP creado.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-path', type=str, required=True)
    parser.add_argument('--output-path', type=str, required=True)
    parser.add_argument('--bot-locale-id', type=str, required=True)
    parser.add_argument('--bot-name', type=str, required=True)
    parser.add_argument('--bot-id', type=str, required=True)
    parser.add_argument('--bot-role-arn', type=str, required=True)

    args = parser.parse_args()

    input_file = os.path.join(args.input_path, 'preprocessed_utterances.csv')
    if not os.path.exists(input_file):
        for root, dirs, files in os.walk(args.input_path):
            for f in files:
                if f.endswith('.csv'):
                    input_file = os.path.join(root, f)
                    break

    if not os.path.exists(args.output_path):
        os.makedirs(args.output_path)
    output_zip = os.path.join(args.output_path, 'lex-import.zip')

    create_lex_import_zip(input_file, output_zip, args.bot_locale_id, args.bot_name, args.bot_id, args.bot_role_arn)

if __name__ == '__main__':
    main()