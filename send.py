"""Publish JSON with a stable ID; repeat the same ID/payload after network failure."""
import argparse
import json
import os
from pathlib import Path
from runtime import check_server_url, json_request, load_env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env')
    parser.add_argument('--id', required=True, help='Stable unique message ID (reuse for retries)')
    parser.add_argument('--file', required=True, help='UTF-8 JSON payload file')
    args = parser.parse_args()
    load_env(args.env)
    payload = json.loads(Path(args.file).read_text(encoding='utf-8'))
    url = check_server_url(os.environ['SERVER_URL'])
    result = json_request(url + '/messages', {'id': args.id, 'payload': payload},
                          os.environ['PRODUCER_TOKEN'])
    print(json.dumps(result))


if __name__ == '__main__':
    main()
