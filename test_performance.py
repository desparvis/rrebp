import os
import time
import logging
import resource
import statistics
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy import event
from werkzeug.serving import make_server

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app import app
from models import db, Broker

# Suppress per-request HTTP log spam so terminal output stays clean
logging.getLogger('werkzeug').setLevel(logging.ERROR)

WRITE_SQL_PREFIXES = (
    'INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'TRUNCATE', 'CREATE', 'REPLACE'
)


def _enforce_readonly_sql(conn, cursor, statement, parameters, context, executemany):
    """Hard safety guard: aborts immediately if any SQL write statement is attempted."""
    cleaned = statement.lstrip()
    first_keyword = cleaned.split(None, 1)[0].upper() if cleaned else ''
    if first_keyword in WRITE_SQL_PREFIXES:
        raise RuntimeError(f"Blocked non-read SQL statement: {first_keyword}")


class TestRREBPSystemPerformance(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = False
        cls.ctx = app.app_context()
        cls.ctx.push()
        event.listen(db.engine, 'before_cursor_execute', _enforce_readonly_sql)

        existing_broker = Broker.query.first()
        cls.sample_license = existing_broker.license_number if existing_broker else 'RWA-2026-0000000000'
        db.session.remove()

        cls.server = make_server('127.0.0.1', 0, app, threaded=True)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        event.remove(db.engine, 'before_cursor_execute', _enforce_readonly_sql)
        db.session.remove()
        cls.ctx.pop()

    def _timed_request(self, path, method='GET', form_data=None, start_event=None):
        if start_event is not None:
            start_event.wait(timeout=15)
        url = f"{self.base_url}{path}"
        payload = urllib.parse.urlencode(form_data).encode('utf-8') if form_data else None
        req = urllib.request.Request(url, data=payload, method=method)
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                resp.read()
                return resp.status, (time.perf_counter() - t0) * 1000.0
        except urllib.error.HTTPError as http_err:
            return http_err.code, (time.perf_counter() - t0) * 1000.0
        except Exception as exc:
            return type(exc).__name__, (time.perf_counter() - t0) * 1000.0

    def _run_concurrent_burst(self, concurrent_users):
        user_actions = [
            ('/', 'GET', None),
            ('/login', 'GET', None),
            ('/properties', 'GET', None),
            ('/broker-rankings', 'GET', None),
            ('/verify', 'POST', {'license_number': self.sample_license}),
        ]
        start_gun = threading.Event()
        statuses = []
        times_ms = []

        with ThreadPoolExecutor(max_workers=concurrent_users) as pool:
            futures = [
                pool.submit(self._timed_request, *user_actions[i % len(user_actions)], start_gun)
                for i in range(concurrent_users)
            ]
            cpu_start = time.process_time()
            wall_start = time.perf_counter()
            # Release all virtual users at the exact same instant
            start_gun.set()

            for fut in as_completed(futures):
                st, ms = fut.result()
                statuses.append(st)
                times_ms.append(ms)

        wall_elapsed = time.perf_counter() - wall_start
        cpu_elapsed = time.process_time() - cpu_start
        rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0

        passed = statuses.count(200)
        failed = concurrent_users - passed
        rps = concurrent_users / wall_elapsed
        cpu_pct = (cpu_elapsed / wall_elapsed) * 100.0
        sorted_ms = sorted(times_ms)
        median_ms = statistics.median(sorted_ms)
        mean_ms = statistics.mean(sorted_ms)
        p95_ms = sorted_ms[int(0.95 * len(sorted_ms)) - 1]
        max_ms = sorted_ms[-1]

        print(
            f"\n[{concurrent_users}-User Simultaneous Load] HTTP_200={passed}/{concurrent_users} (Failed={failed}), "
            f"Time={wall_elapsed:.2f}s, Throughput={rps:.2f} req/s, "
            f"Mean={mean_ms:.1f}ms, Median={median_ms:.1f}ms, P95={p95_ms:.1f}ms, Max={max_ms:.1f}ms, "
            f"CPU={cpu_pct:.1f}%, PeakRAM={rss_mb:.1f}MB"
        )
        return passed, statuses

    def test_ST01_single_user_baseline_latency(self):
        """ST-01: Measure single-user baseline latency across core public and Supabase routes."""
        routes = [
            ('/', 'GET', None),
            ('/login', 'GET', None),
            ('/properties', 'GET', None),
            ('/broker-rankings', 'GET', None),
            ('/verify', 'POST', {'license_number': self.sample_license}),
        ]
        latencies = {}
        for path, method, data in routes:
            status, ms = self._timed_request(path, method, data)
            self.assertEqual(status, 200)
            latencies[f"{method} {path}"] = round(ms, 1)

        print(f"\n[ST-01 Baseline Latency ms] {latencies}")

    def test_ST02_concurrent_50_users_load(self):
        """ST-02: Simulate 50 simultaneous users hitting RREBP concurrently."""
        passed, statuses = self._run_concurrent_burst(50)
        self.assertEqual(passed, 50, f"Non-200 responses under 50-user load: {statuses}")

    def test_ST03_concurrent_100_users_stress_load(self):
        """ST-03: Simulate 100 simultaneous users hitting RREBP at the same instant."""
        passed, statuses = self._run_concurrent_burst(100)
        self.assertEqual(passed, 100, f"Non-200 responses under 100-user load: {statuses}")


if __name__ == '__main__':
    unittest.main(verbosity=2)