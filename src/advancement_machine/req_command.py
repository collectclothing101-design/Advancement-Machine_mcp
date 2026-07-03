import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .base_command import BaseCommand

class ReqCommand(BaseCommand):
    def __init__(self):
        super().__init__("req", "Send HTTP request with evasion fingerprints")

    def configure(self, parser):
        parser.add_argument("method", choices=["GET", "POST", "PUT", "DELETE", "HEAD"])
        parser.add_argument("url", help="Target URL")
        parser.add_argument("-H", "--header", action="append", default=[], help="Header: Key:Value")
        parser.add_argument("-d", "--data", help="Body data (string or @file)")
        parser.add_argument("--proxy", help="Proxy URL (http://user:pass@host:port)")
        parser.add_argument("--timeout", type=float, default=10.0)
        parser.add_argument("--retries", type=int, default=2)

    def execute(self, args):
        session = requests.Session()
        if args["retries"] > 0:
            retry = Retry(total=args["retries"], backoff_factor=1)
            adapter = HTTPAdapter(max_retries=retry)
            session.mount("http://", adapter)
            session.mount("https://", adapter)

        if args["proxy"]:
            session.proxies = {"http": args["proxy"], "https": args["proxy"]}

        headers = {}
        for h in args["header"]:
            if ":" in h:
                k, v = h.split(":", 1)
                headers[k.strip()] = v.strip()

        data = None
        if args["data"]:
            if args["data"].startswith("@"):
                with open(args["data"][1:], "r") as f:
                    data = f.read()
            else:
                data = args["data"]

        try:
            resp = session.request(
                method=args["method"],
                url=args["url"],
                headers=headers,
                data=data,
                timeout=args["timeout"]
            )
            return {
                "status": resp.status_code,
                "headers": dict(resp.headers),
                "body": resp.text[:10000]
            }
        except Exception as e:
            return {"error": str(e)}