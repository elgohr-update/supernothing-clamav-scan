import boto3
import clamd
import requests

from libpolyd import transaction, api

from . import logging

logger = logging.get_logger()


def get_client(access_key, secret_key, endpoint, region):
    session = boto3.session.Session(access_key, secret_key, region_name=region)
    return session.client('s3', endpoint_url=endpoint)


def scan_obj(file_obj, clamav_host):
    c = clamd.ClamdNetworkSocket(clamav_host)
    return c.instream(file_obj)


def scan_url(url, clamav_host, session=None):
    session = session or requests.Session()
    with session.get(url, stream=True) as r:
        r.raise_for_status()
        return scan_obj(r.raw, clamav_host)


def scan_s3(bucket, key, client, clamav_host):
    try:
        result = scan_obj(client.get_object(Bucket=bucket, Key=key)['Body'], clamav_host)
    except Exception as e:
        logger.exception('Scan failed: %s', e)
        raise e
    return result


# TODO in the future, this should collect from multiple engines
def scan_event(event, client, clamav_host, api, eth_key):
    bucket, key = event.path.split('/', 1)
    result = scan_s3(bucket, key, client, clamav_host)
    logger.info('Scan result: %s', result)
    verdict, family = result['stream']
    if 'verdict' == 'OK':
        verdict = False
        metadata = {'malware_family': '', 'scanner':  {'version': 'acqcuire_nectar 0.69'}}
    else:
        verdict = True
        metadata = {'malware_family': family, 'scanner': {'version': 'acqcuire_nectar 0.69'}}

    # lol improve once settles happen
    bid = 420000000000000000

    guid = event.bounty['data']['guid']
    a = transaction.Assertion(guid, verdict, bid, metadata).sign(eth_key)
    logger.info('Posting assertion: %s', a)
    r = api.post_assertion(guid, a)
    logger.info('Posted assertion: %s', a)

    event.ack()

    return result, event
