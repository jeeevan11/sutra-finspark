"""The synthetic bank world — generated once from SEED, identical every run.

All IDs are obviously synthetic (CUST-0421, ACC-0421-01); no realistic PII formats.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

# Indian cities (name -> lat, lon) for geo + impossible-travel distances.
CITIES: dict[str, tuple[float, float]] = {
    "Mumbai": (19.076, 72.877), "Pune": (18.520, 73.856), "Nagpur": (21.146, 79.088),
    "Nashik": (19.997, 73.789), "Aurangabad": (19.876, 75.343), "Delhi": (28.613, 77.209),
    "Bengaluru": (12.972, 77.594), "Chennai": (13.083, 80.270), "Kolkata": (22.573, 88.364),
    "Hyderabad": (17.385, 78.487), "Ahmedabad": (23.023, 72.571), "Jaipur": (26.912, 75.787),
    "Lucknow": (26.847, 80.947), "Surat": (21.170, 72.831), "Indore": (22.720, 75.858),
    "Bhopal": (23.260, 77.413), "Patna": (25.594, 85.138), "Kochi": (9.932, 76.267),
    "Panaji": (15.491, 73.828), "Solapur": (17.660, 75.906),
}

# Foreign geos used only by attack scenarios.
FOREIGN_GEOS: dict[str, tuple[float, float]] = {
    "Bucharest": (44.427, 26.103), "Chisinau": (47.011, 28.858), "Lagos": (6.524, 3.379),
    "Phnom Penh": (11.556, 104.928), "Tbilisi": (41.716, 44.783),
}

ALL_GEOS = {**CITIES, **FOREIGN_GEOS}

MALWARE_FAMILIES = ["CobaltStrike-beacon", "AgentTesla", "Emotet", "AsyncRAT", "QakBot"]

FIRST = ["Aarav", "Vivaan", "Ishaan", "Diya", "Ananya", "Kavya", "Rohan", "Meera",
         "Arjun", "Sanya", "Kabir", "Nisha", "Dev", "Pooja", "Rahul", "Sneha"]
LAST = ["Sharma", "Patil", "Deshmukh", "Kulkarni", "Joshi", "Iyer", "Reddy", "Gupta",
        "Singh", "Nair", "Chavan", "Pawar", "Mehta", "Bose", "Das", "Rao"]


def haversine_km(a: str, b: str) -> float:
    la1, lo1 = ALL_GEOS[a]
    la2, lo2 = ALL_GEOS[b]
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = math.radians(la2 - la1), math.radians(lo2 - lo1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


@dataclass
class Customer:
    customer_id: str
    name: str
    segment: str                    # "retail" | "business"
    accounts: list[str]
    devices: list[str]
    home_geo: str
    asns: list[str]                 # home ISP ASNs (1-2)
    ips: list[str]
    daily_outflow_mean: float       # INR
    daily_outflow_std: float
    active_hours: tuple[int, int]   # IST hours [start, end)
    payees: list[str]
    account_age_days: int
    dormant: bool


@dataclass
class Staff:
    staff_id: str
    terminal_id: str
    branch_ip: str
    hours: tuple[float, float] = (9.5, 18.5)  # IST


@dataclass
class Server:
    server_id: str
    # weighted key-exchange profile for benign TLS noise
    kex_weights: dict[str, float] = field(default_factory=dict)


@dataclass
class World:
    seed: int
    customers: dict[str, Customer]
    accounts: dict[str, str]                  # account_id -> customer_id
    dormant_accounts: set[str]
    staff: dict[str, Staff]
    terminals: dict[str, str]                 # terminal_id -> staff_id
    servers: dict[str, Server]
    branch_ips: list[str]
    benign_asns: list[str]
    hostile_asns: list[str]
    known_tls_dsts: list[str]
    payee_pool: list[str]
    # fixed demo anchors
    victim_customer: str = "CUST-0421"
    compromised_terminal: str = "TERM-114"
    compromised_staff: str = "STAFF-77"
    exfil_server: str = "DB-2"
    scenario_b_account: str = ""

    def customer_of_account(self, account_id: str) -> Customer:
        return self.customers[self.accounts[account_id]]


def _ip(rng: random.Random) -> str:
    return f"10.{rng.randint(1, 250)}.{rng.randint(1, 250)}.{rng.randint(2, 250)}"


def _public_ip(rng: random.Random) -> str:
    return f"{rng.choice([49, 103, 117, 152, 182])}.{rng.randint(10, 250)}.{rng.randint(1, 250)}.{rng.randint(2, 250)}"


def build_world(seed: int) -> World:
    rng = random.Random(seed)
    cities = list(CITIES)

    benign_asns = [f"AS{n}" for n in sorted(rng.sample(range(9000, 60000), 30))]
    hostile_asns = [f"AS{n}" for n in sorted(rng.sample(range(60001, 65500), 6))]

    payee_pool = [f"PAYEE-{i:04d}" for i in range(1, 400)]

    customers: dict[str, Customer] = {}
    accounts: dict[str, str] = {}
    dormant_accounts: set[str] = set()

    for i in range(1, 501):
        cid = f"CUST-{i:04d}"
        segment = "business" if rng.random() < 0.10 else "retail"
        n_acc = rng.choice([1, 1, 1, 2])
        accs = [f"ACC-{i:04d}-{n:02d}" for n in range(1, n_acc + 1)]
        devices = [f"DEV-{rng.randrange(16**6):06X}" for _ in range(rng.choice([1, 2, 2, 3]))]
        home = rng.choice(cities)
        asns = rng.sample(benign_asns, rng.choice([1, 2]))
        if segment == "business":
            mean = rng.uniform(80_000, 500_000)
            hours = (9, 19)
        else:
            mean = math.exp(rng.uniform(math.log(3_000), math.log(40_000)))
            start = rng.randint(7, 11)
            hours = (start, min(23, start + rng.randint(10, 14)))
        dormant = rng.random() < 0.05
        cust = Customer(
            customer_id=cid,
            name=f"{rng.choice(FIRST)} {rng.choice(LAST)}",
            segment=segment,
            accounts=accs,
            devices=devices,
            home_geo=home,
            asns=asns,
            ips=[_public_ip(rng) for _ in range(2)],
            daily_outflow_mean=round(mean, 2),
            daily_outflow_std=round(mean * rng.uniform(0.25, 0.6), 2),
            active_hours=hours,
            payees=rng.sample(payee_pool, rng.randint(5, 15)),
            account_age_days=rng.randint(90, 4000),
            dormant=dormant,
        )
        customers[cid] = cust
        for a in accs:
            accounts[a] = cid
            if dormant:
                dormant_accounts.add(a)

    # Demo anchors — force the victim to be an active retail customer with a modest
    # baseline so the structuring txns are unmistakably anomalous.
    victim = customers["CUST-0421"]
    victim.segment = "retail"
    victim.dormant = False
    victim.daily_outflow_mean = 8_400.0
    victim.daily_outflow_std = 3_100.0
    victim.active_hours = (8, 22)
    for a in victim.accounts:
        dormant_accounts.discard(a)

    # Scenario B target: a dormant business account (attacker drains a quiet corporate
    # account through the compromised terminal).
    b_cust = customers["CUST-0107"]
    b_cust.segment = "business"
    b_cust.dormant = True
    b_cust.daily_outflow_mean = 260_000.0
    b_cust.daily_outflow_std = 90_000.0
    scenario_b_account = b_cust.accounts[0]
    for a in b_cust.accounts:
        dormant_accounts.add(a)

    branch_ips = [_ip(rng) for _ in range(25)]
    staff_nums = sorted(rng.sample([n for n in range(10, 99) if n != 77], 39)) + [77]
    staff: dict[str, Staff] = {}
    terminals: dict[str, str] = {}
    for idx, n in enumerate(sorted(staff_nums)):
        sid = f"STAFF-{n:02d}"
        tid = "TERM-114" if n == 77 else f"TERM-{200 + idx}"
        st = Staff(staff_id=sid, terminal_id=tid, branch_ip=branch_ips[idx % len(branch_ips)])
        staff[sid] = st
        terminals[tid] = sid

    # Declared crypto posture drives benign TLS noise and the /quantum inventory:
    # APP-1 fully hybrid (green), DB-1/DB-2 classical X25519 (amber — DB-2 goes red
    # only when Scenario C pushes RSA-2048 exfil through it), APP-2 legacy (red).
    servers = {
        "DB-1": Server("DB-1", {"X25519": 0.7, "X25519Kyber768-hybrid": 0.3}),
        "DB-2": Server("DB-2", {"X25519": 1.0}),
        "APP-1": Server("APP-1", {"X25519Kyber768-hybrid": 1.0}),
        "APP-2": Server("APP-2", {"ECDHE-P256": 0.55, "RSA-2048": 0.25, "X25519": 0.2}),
    }
    known_tls_dsts = [_ip(rng) for _ in range(12)]

    return World(
        seed=seed,
        customers=customers,
        accounts=accounts,
        dormant_accounts=dormant_accounts,
        staff=staff,
        terminals=terminals,
        servers=servers,
        branch_ips=branch_ips,
        benign_asns=benign_asns,
        hostile_asns=hostile_asns,
        known_tls_dsts=known_tls_dsts,
        payee_pool=payee_pool,
        scenario_b_account=scenario_b_account,
    )
