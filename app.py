import os
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd
import streamlit as st
import mysql.connector
from mysql.connector import Error


# ============================================================
# SMART TOUR - APP ĐẶT TOUR DU LỊCH
# Streamlit + MySQL Aiven
# ============================================================
# Chạy:
#   pip install -r requirements.txt
#   streamlit run app.py
#
# AIVEN MYSQL:
# Thông tin kết nối đã được đặt theo tài khoản Aiven của bạn.
# Nếu Aiven thay đổi mật khẩu, chỉ cần sửa DB_CONFIG bên dưới.
# ============================================================

st.set_page_config(
    page_title="SMART TOUR - Đặt tour",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)
DB_CONFIG = {
    "host": "mysql-1b346c1b-kimchi8019-4ea9.e.aivencloud.com",
    "port": 21314,
    "user": "avnadmin",
    "password": "AVNS_ZuLUVTHk6cKBskjg0Kp",
    "database": "defaultdb",
    "autocommit": False,
    "connection_timeout": 15,
    "ssl_disabled": False,
}

# Nếu Aiven yêu cầu xác thực CA nghiêm ngặt, tải CA certificate
# và điền đường dẫn tại đây. Để trống vẫn dùng TLS.
SSL_CA_PATH = ""

MONEY_Q = Decimal("1")


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
<style>
.stApp { background:#f5f7fb; }
.hero {
    padding:32px;
    border-radius:20px;
    background:linear-gradient(135deg,#0757b8,#2d9cff);
    color:white;
    margin-bottom:22px;
}
.hero h1,.hero h2,.hero p { color:white !important; }
.card {
    background:white;
    padding:20px;
    border-radius:16px;
    box-shadow:0 2px 12px rgba(0,0,0,.07);
    margin-bottom:16px;
}
.price {
    color:#0757b8;
    font-size:24px;
    font-weight:800;
}
.total {
    color:#0b5ed7;
    font-size:30px;
    font-weight:900;
}
.note {
    padding:12px 16px;
    background:#eef6ff;
    border-left:4px solid #0b5ed7;
    border-radius:8px;
}
.warning {
    padding:12px 16px;
    background:#fff8e6;
    border-left:4px solid #f0a000;
    border-radius:8px;
}
[data-testid="stMetric"] {
    background:white;
    padding:14px;
    border-radius:12px;
    box-shadow:0 2px 8px rgba(0,0,0,.05);
}
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# BASIC HELPERS
# ============================================================

def money(value):
    try:
        d = Decimal(str(value)).quantize(MONEY_Q, rounding=ROUND_HALF_UP)
        return f"{d:,.0f} VNĐ"
    except Exception:
        return "0 VNĐ"


def dec(value):
    return Decimal(str(value or 0))


def clean(value):
    return str(value).strip() if value is not None else ""


def age_category(age):
    """Pricing/occupancy category:
       0-1: infant
       2-5: young child
       6-10: child
       11+: adult
    """
    age = int(age)
    if age <= 1:
        return "infant"
    if age <= 5:
        return "young_child"
    if age <= 10:
        return "child"
    return "adult"


def child_multiplier(age):
    # Có thể thay đổi theo chính sách từng tour.
    category = age_category(age)
    return {
        "infant": Decimal("0.00"),
        "young_child": Decimal("0.50"),
        "child": Decimal("0.70"),
        "adult": Decimal("1.00"),
    }[category]


def category_label(category):
    return {
        "infant": "Em bé (0–1 tuổi)",
        "young_child": "Trẻ nhỏ (2–5 tuổi)",
        "child": "Trẻ em (6–10 tuổi)",
        "adult": "Người lớn (11+ tuổi)",
    }.get(category, category)


def hash_text(value):
    # Không dùng cho mật khẩu ở bản này; khách chỉ đặt tour bằng tên + SĐT.
    import hashlib
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ============================================================
# DATABASE
# ============================================================

def connect_db():
    config = DB_CONFIG.copy()
    if SSL_CA_PATH:
        config["ssl_ca"] = SSL_CA_PATH
        config["ssl_verify_cert"] = True
        config["ssl_verify_identity"] = True
    return mysql.connector.connect(**config)


def execute(sql, params=(), fetch="none"):
    conn = None
    cur = None
    try:
        conn = connect_db()
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)

        if fetch == "one":
            return cur.fetchone()
        if fetch == "all":
            return cur.fetchall()

        conn.commit()
        return cur.lastrowid
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if cur:
            cur.close()
        if conn and conn.is_connected():
            conn.close()


def query_df(sql, params=()):
    conn = None
    try:
        conn = connect_db()
        return pd.read_sql(sql, conn, params=params)
    finally:
        if conn and conn.is_connected():
            conn.close()


def init_db():
    conn = connect_db()
    cur = conn.cursor()

    try:
        # --------------------------------------------------------
        # TOURS
        # --------------------------------------------------------
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tours (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                destination VARCHAR(200) NOT NULL,
                duration VARCHAR(100) NOT NULL,
                days INT NOT NULL DEFAULT 1,
                nights INT NOT NULL DEFAULT 0,
                adult_price DECIMAL(15,2) NOT NULL DEFAULT 0,
                child_price DECIMAL(15,2) NOT NULL DEFAULT 0,
                infant_price DECIMAL(15,2) NOT NULL DEFAULT 0,
                max_people INT NOT NULL DEFAULT 30,
                available_seats INT NOT NULL DEFAULT 30,
                description VARCHAR(2000) DEFAULT '',
                interests VARCHAR(500) DEFAULT '',
                status VARCHAR(30) NOT NULL DEFAULT 'Đang mở',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

        # --------------------------------------------------------
        # HOTELS
        # --------------------------------------------------------
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS hotels (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                destination VARCHAR(200) NOT NULL,
                stars INT NOT NULL DEFAULT 3,
                description VARCHAR(1000) DEFAULT '',
                status VARCHAR(30) NOT NULL DEFAULT 'Đang hoạt động',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

        # --------------------------------------------------------
        # HOTEL ROOM RATES
        # regular_price / peak_price cho phép giá phòng thay đổi
        # theo mùa và ngày khởi hành.
        # --------------------------------------------------------
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS hotel_room_rates (
                id INT AUTO_INCREMENT PRIMARY KEY,
                hotel_id INT NOT NULL,
                room_type VARCHAR(120) NOT NULL,
                max_guests INT NOT NULL DEFAULT 2,
                regular_price DECIMAL(15,2) NOT NULL DEFAULT 0,
                peak_price DECIMAL(15,2) NOT NULL DEFAULT 0,
                extra_adult_price DECIMAL(15,2) NOT NULL DEFAULT 0,
                extra_child_price DECIMAL(15,2) NOT NULL DEFAULT 0,
                breakfast_included TINYINT(1) NOT NULL DEFAULT 1,
                inventory INT NOT NULL DEFAULT 20,
                status VARCHAR(30) NOT NULL DEFAULT 'Đang bán',
                UNIQUE KEY uq_hotel_room_type (hotel_id, room_type),
                FOREIGN KEY (hotel_id) REFERENCES hotels(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

        # --------------------------------------------------------
        # PEAK SEASONS
        # --------------------------------------------------------
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS peak_seasons (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(150) NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'Đang áp dụng'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

        # --------------------------------------------------------
        # MEALS
        # --------------------------------------------------------
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS meals (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                destination VARCHAR(200) DEFAULT '',
                meal_type VARCHAR(50) NOT NULL,
                adult_price DECIMAL(15,2) NOT NULL DEFAULT 0,
                child_price DECIMAL(15,2) NOT NULL DEFAULT 0,
                infant_price DECIMAL(15,2) NOT NULL DEFAULT 0,
                description VARCHAR(500) DEFAULT '',
                status VARCHAR(30) NOT NULL DEFAULT 'Đang bán'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

        # --------------------------------------------------------
        # TRANSPORTS
        # --------------------------------------------------------
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS transports (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                vehicle_type VARCHAR(100) NOT NULL,
                capacity INT NOT NULL DEFAULT 16,
                price_per_person DECIMAL(15,2) NOT NULL DEFAULT 0,
                price_per_trip DECIMAL(15,2) NOT NULL DEFAULT 0,
                description VARCHAR(500) DEFAULT '',
                status VARCHAR(30) NOT NULL DEFAULT 'Đang bán'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

        # --------------------------------------------------------
        # BOOKINGS
        # --------------------------------------------------------
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                booking_code VARCHAR(40) UNIQUE NOT NULL,
                customer_name VARCHAR(150) NOT NULL,
                customer_phone VARCHAR(30) NOT NULL,
                tour_id INT NOT NULL,
                departure_date DATE NOT NULL,
                adults INT NOT NULL DEFAULT 0,
                children INT NOT NULL DEFAULT 0,
                young_children INT NOT NULL DEFAULT 0,
                infants INT NOT NULL DEFAULT 0,
                total_people INT NOT NULL DEFAULT 0,
                room_type VARCHAR(120) DEFAULT '',
                rooms INT NOT NULL DEFAULT 0,
                hotel_id INT NULL,
                meal_id INT NULL,
                transport_id INT NULL,
                tour_amount DECIMAL(15,2) NOT NULL DEFAULT 0,
                hotel_amount DECIMAL(15,2) NOT NULL DEFAULT 0,
                meal_amount DECIMAL(15,2) NOT NULL DEFAULT 0,
                transport_amount DECIMAL(15,2) NOT NULL DEFAULT 0,
                total_amount DECIMAL(15,2) NOT NULL DEFAULT 0,
                status VARCHAR(40) NOT NULL DEFAULT 'Chờ xác nhận',
                note VARCHAR(2000) DEFAULT '',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tour_id) REFERENCES tours(id),
                FOREIGN KEY (hotel_id) REFERENCES hotels(id) ON DELETE SET NULL,
                FOREIGN KEY (meal_id) REFERENCES meals(id) ON DELETE SET NULL,
                FOREIGN KEY (transport_id) REFERENCES transports(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

        # --------------------------------------------------------
        # SEED DATA - chỉ thêm nếu bảng đang trống.
        # --------------------------------------------------------
        cur.execute("SELECT COUNT(*) AS n FROM tours")
        if cur.fetchone()["n"] == 0:
            tours = [
                (
                    "Vũng Tàu 2N1Đ - Biển & Di sản",
                    "Vũng Tàu",
                    "2 ngày 1 đêm",
                    2, 1, 1250000, 875000, 0,
                    30, 30,
                    "Bạch Dinh, biển Vũng Tàu, Núi Nhỏ, ẩm thực địa phương.",
                    "biển, nghỉ dưỡng, văn hóa, lịch sử",
                ),
                (
                    "Đà Lạt 3N2Đ - Thành phố ngàn hoa",
                    "Đà Lạt",
                    "3 ngày 2 đêm",
                    3, 2, 2950000, 2065000, 0,
                    30, 30,
                    "Tham quan các điểm nổi bật, nghỉ dưỡng và trải nghiệm ẩm thực.",
                    "núi, nghỉ dưỡng, thiên nhiên, check-in",
                ),
                (
                    "Nha Trang 3N2Đ - Biển đảo",
                    "Nha Trang",
                    "3 ngày 2 đêm",
                    3, 2, 3150000, 2205000, 0,
                    40, 40,
                    "Biển, đảo, ẩm thực và thời gian nghỉ ngơi hợp lý.",
                    "biển, đảo, nghỉ dưỡng, gia đình",
                ),
                (
                    "Phú Quốc 4N3Đ - Nghỉ dưỡng",
                    "Phú Quốc",
                    "4 ngày 3 đêm",
                    4, 3, 4950000, 3465000, 0,
                    30, 30,
                    "Nghỉ dưỡng, biển đảo và trải nghiệm địa phương.",
                    "biển, đảo, nghỉ dưỡng",
                ),
            ]
            cur.executemany(
                """
                INSERT INTO tours
                (name,destination,duration,days,nights,adult_price,child_price,
                 infant_price,max_people,available_seats,description,interests)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                tours,
            )

        cur.execute("SELECT COUNT(*) AS n FROM hotels")
        if cur.fetchone()["n"] == 0:
            hotels = [
                ("Khách sạn Biển Xanh", "Vũng Tàu", 3, "Gần biển, phù hợp gia đình."),
                ("Khách sạn Bạch Dinh", "Vũng Tàu", 4, "Không gian nghỉ dưỡng cao cấp."),
                ("Đà Lạt Garden Hotel", "Đà Lạt", 3, "Gần trung tâm."),
                ("Nha Trang Xanh Hotel", "Nha Trang", 4, "Gần biển."),
                ("Phú Quốc Ocean Resort", "Phú Quốc", 4, "Khu nghỉ dưỡng biển."),
            ]
            cur.executemany(
                """
                INSERT INTO hotels(name,destination,stars,description)
                VALUES (%s,%s,%s,%s)
                """,
                hotels,
            )

        cur.execute("SELECT COUNT(*) AS n FROM hotel_room_rates")
        if cur.fetchone()["n"] == 0:
            cur.execute("SELECT id,name FROM hotels")
            hmap = {r["name"]: r["id"] for r in cur.fetchall()}

            rooms = [
                (hmap["Khách sạn Biển Xanh"], "Standard", 2, 650000, 800000, 200000, 100000, 1, 30),
                (hmap["Khách sạn Biển Xanh"], "Deluxe", 3, 850000, 1050000, 250000, 120000, 1, 20),
                (hmap["Khách sạn Bạch Dinh"], "Deluxe", 2, 1200000, 1500000, 350000, 150000, 1, 20),
                (hmap["Khách sạn Bạch Dinh"], "Family", 4, 1650000, 2050000, 350000, 150000, 1, 10),
                (hmap["Đà Lạt Garden Hotel"], "Standard", 2, 700000, 900000, 200000, 100000, 1, 30),
                (hmap["Đà Lạt Garden Hotel"], "Family", 4, 1350000, 1700000, 250000, 120000, 1, 15),
                (hmap["Nha Trang Xanh Hotel"], "Deluxe", 2, 950000, 1200000, 250000, 120000, 1, 20),
                (hmap["Nha Trang Xanh Hotel"], "Family", 4, 1750000, 2200000, 300000, 150000, 1, 10),
                (hmap["Phú Quốc Ocean Resort"], "Deluxe", 2, 1450000, 1900000, 400000, 180000, 1, 20),
                (hmap["Phú Quốc Ocean Resort"], "Family", 4, 2450000, 3100000, 450000, 200000, 1, 10),
            ]
            cur.executemany(
                """
                INSERT INTO hotel_room_rates
                (hotel_id,room_type,max_guests,regular_price,peak_price,
                 extra_adult_price,extra_child_price,breakfast_included,inventory)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                rooms,
            )

        cur.execute("SELECT COUNT(*) AS n FROM peak_seasons")
        if cur.fetchone()["n"] == 0:
            current_year = date.today().year
            seasons = [
                ("Tết/Du lịch đầu năm", date(current_year, 1, 20), date(current_year, 2, 20)),
                ("Lễ 30/4 - 1/5", date(current_year, 4, 28), date(current_year, 5, 3)),
                ("Mùa hè", date(current_year, 6, 1), date(current_year, 8, 31)),
                ("Quốc khánh", date(current_year, 8, 30), date(current_year, 9, 3)),
            ]
            # Chỉ thêm những khoảng ngày hợp lệ của năm hiện tại.
            cur.executemany(
                """
                INSERT INTO peak_seasons(name,start_date,end_date)
                VALUES (%s,%s,%s)
                """,
                seasons,
            )

        cur.execute("SELECT COUNT(*) AS n FROM meals")
        if cur.fetchone()["n"] == 0:
            meals = [
                ("Set Vũng Tàu", "Vũng Tàu", "Trưa", 140000, 98000, 0, "Set đoàn."),
                ("Set Vũng Tàu Hải sản", "Vũng Tàu", "Tối", 220000, 154000, 0, "Hải sản."),
                ("Set Đà Lạt", "Đà Lạt", "Trưa", 150000, 105000, 0, "Đặc sản địa phương."),
                ("Set Đà Lạt", "Đà Lạt", "Tối", 180000, 126000, 0, "Set tối."),
                ("Set Nha Trang", "Nha Trang", "Trưa", 160000, 112000, 0, "Hải sản."),
                ("Set Nha Trang", "Nha Trang", "Tối", 200000, 140000, 0, "Set tối."),
                ("Set Phú Quốc", "Phú Quốc", "Trưa", 200000, 140000, 0, "Hải sản."),
                ("Set Phú Quốc", "Phú Quốc", "Tối", 250000, 175000, 0, "Set tối."),
            ]
            cur.executemany(
                """
                INSERT INTO meals
                (name,destination,meal_type,adult_price,child_price,infant_price,description)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                meals,
            )

        cur.execute("SELECT COUNT(*) AS n FROM transports")
        if cur.fetchone()["n"] == 0:
            transports = [
                ("Xe 16 chỗ", "16 chỗ", 16, 180000, 0, "Nhóm nhỏ."),
                ("Xe 29 chỗ", "29 chỗ", 29, 220000, 0, "Đoàn vừa."),
                ("Xe 45 chỗ", "45 chỗ", 45, 260000, 0, "Đoàn lớn."),
                ("Xe riêng 7 chỗ", "7 chỗ", 7, 350000, 0, "Gia đình/nhóm nhỏ."),
            ]
            cur.executemany(
                """
                INSERT INTO transports
                (name,vehicle_type,capacity,price_per_person,price_per_trip,description)
                VALUES (%s,%s,%s,%s,%s,%s)
                """,
                transports,
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


# ============================================================
# DATA ACCESS
# ============================================================

def get_tours():
    return query_df(
        """
        SELECT * FROM tours
        WHERE status='Đang mở'
        ORDER BY id DESC
        """
    )


def get_tour(tour_id):
    return execute(
        "SELECT * FROM tours WHERE id=%s",
        (tour_id,),
        fetch="one",
    )


def get_hotels(destination):
    return execute(
        """
        SELECT * FROM hotels
        WHERE status='Đang hoạt động'
        AND destination=%s
        ORDER BY stars DESC, name
        """,
        (destination,),
        fetch="all",
    )


def get_room_rates(hotel_id):
    return execute(
        """
        SELECT * FROM hotel_room_rates
        WHERE hotel_id=%s AND status='Đang bán'
        ORDER BY regular_price
        """,
        (hotel_id,),
        fetch="all",
    )


def get_meals(destination):
    return execute(
        """
        SELECT * FROM meals
        WHERE status='Đang bán'
        AND (destination=%s OR destination='')
        ORDER BY meal_type,name
        """,
        (destination,),
        fetch="all",
    )


def get_transports():
    return execute(
        """
        SELECT * FROM transports
        WHERE status='Đang bán'
        ORDER BY capacity
        """,
        fetch="all",
    )


def is_peak(departure_date):
    row = execute(
        """
        SELECT id,name FROM peak_seasons
        WHERE status='Đang áp dụng'
        AND %s BETWEEN start_date AND end_date
        LIMIT 1
        """,
        (departure_date,),
        fetch="one",
    )
    return row


def get_existing_bookings(tour_id, departure_date):
    row = execute(
        """
        SELECT COALESCE(SUM(total_people),0) AS total_people
        FROM bookings
        WHERE tour_id=%s
        AND departure_date=%s
        AND status NOT IN ('Đã hủy')
        """,
        (tour_id, departure_date),
        fetch="one",
    )
    return int(row["total_people"] or 0)


# ============================================================
# PRICE CALCULATION
# ============================================================

def calculate_room_need(adults, young_children, children, infants, room_capacity):
    # Em bé không tính chỗ ngủ riêng mặc định.
    sleeping_people = adults + young_children + children
    return max(1, (sleeping_people + room_capacity - 1) // room_capacity)


def calculate_price(
    tour,
    departure_date,
    guest_ages,
    room_rate=None,
    rooms=0,
    meal=None,
    transport=None,
):
    adults = sum(1 for a in guest_ages if age_category(a) == "adult")
    children = sum(1 for a in guest_ages if age_category(a) == "child")
    young_children = sum(
        1 for a in guest_ages if age_category(a) == "young_child"
    )
    infants = sum(1 for a in guest_ages if age_category(a) == "infant")

    # Giá tour:
    # adult = 100%
    # 6-10 = 70%
    # 2-5 = 50%
    # 0-1 = miễn phí phần tour cơ bản
    tour_amount = (
        Decimal(adults) * dec(tour["adult_price"])
        + Decimal(children) * dec(tour["child_price"])
        + Decimal(young_children)
        * dec(tour["adult_price"])
        * Decimal("0.50")
        + Decimal(infants) * dec(tour["infant_price"])
    )

    hotel_amount = Decimal("0")
    room_unit = Decimal("0")
    peak_info = is_peak(departure_date)

    if room_rate and rooms > 0:
        room_unit = (
            dec(room_rate["peak_price"])
            if peak_info
            else dec(room_rate["regular_price"])
        )
        hotel_amount = (
            room_unit
            * Decimal(rooms)
            * Decimal(int(tour["nights"]))
        )

        # Extra person charge nếu vượt sức chứa phòng.
        capacity = int(room_rate["max_guests"])
        included = capacity * rooms
        sleeping_people = adults + young_children + children
        extra = max(0, sleeping_people - included)

        # Ưu tiên tính người lớn trước, sau đó trẻ em.
        extra_adults = min(extra, adults)
        extra_children = max(0, extra - extra_adults)

        hotel_amount += (
            Decimal(extra_adults) * dec(room_rate["extra_adult_price"])
            + Decimal(extra_children) * dec(room_rate["extra_child_price"])
        )

    meal_amount = Decimal("0")
    if meal:
        meal_amount = (
            Decimal(adults) * dec(meal["adult_price"])
            + Decimal(children) * dec(meal["child_price"])
            + Decimal(young_children) * dec(meal["child_price"])
            + Decimal(infants) * dec(meal["infant_price"])
        )

    transport_amount = Decimal("0")
    if transport:
        total_people = len(guest_ages)
        transport_amount = (
            Decimal(total_people) * dec(transport["price_per_person"])
            + dec(transport["price_per_trip"])
        )

    total = tour_amount + hotel_amount + meal_amount + transport_amount

    return {
        "adults": adults,
        "children": children,
        "young_children": young_children,
        "infants": infants,
        "tour_amount": tour_amount,
        "hotel_amount": hotel_amount,
        "meal_amount": meal_amount,
        "transport_amount": transport_amount,
        "room_unit": room_unit,
        "total": total,
        "peak": bool(peak_info),
        "peak_name": peak_info["name"] if peak_info else "",
    }


# ============================================================
# BOOKING
# ============================================================

def create_booking(
    customer_name,
    customer_phone,
    tour_id,
    departure_date,
    guest_ages,
    room_type,
    rooms,
    hotel_id,
    meal_id,
    transport_id,
    amounts,
    note,
):
    booking_code = "ST" + datetime.now().strftime("%Y%m%d%H%M%S%f")[-12:]

    result = execute(
        """
        INSERT INTO bookings
        (
            booking_code,customer_name,customer_phone,tour_id,departure_date,
            adults,children,young_children,infants,total_people,
            room_type,rooms,hotel_id,meal_id,transport_id,
            tour_amount,hotel_amount,meal_amount,transport_amount,total_amount,
            status,note
        )
        VALUES
        (%s,%s,%s,%s,%s,
         %s,%s,%s,%s,%s,
         %s,%s,%s,%s,%s,
         %s,%s,%s,%s,%s,
         'Chờ xác nhận',%s)
        """,
        (
            booking_code,
            customer_name,
            customer_phone,
            tour_id,
            departure_date,
            amounts["adults"],
            amounts["children"],
            amounts["young_children"],
            amounts["infants"],
            len(guest_ages),
            room_type,
            rooms,
            hotel_id,
            meal_id,
            transport_id,
            amounts["tour_amount"],
            amounts["hotel_amount"],
            amounts["meal_amount"],
            amounts["transport_amount"],
            amounts["total"],
            note,
        ),
    )
    return booking_code


def get_booking(booking_code):
    return execute(
        """
        SELECT
            b.*,
            t.name AS tour_name,
            t.destination,
            h.name AS hotel_name
        FROM bookings b
        JOIN tours t ON t.id=b.tour_id
        LEFT JOIN hotels h ON h.id=b.hotel_id
        WHERE b.booking_code=%s
        """,
        (booking_code,),
        fetch="one",
    )


# ============================================================
# APP STARTUP
# ============================================================

try:
    init_db()
except Exception as exc:
    st.error("❌ Không thể kết nối MySQL Aiven.")
    st.code(f"{type(exc).__name__}: {exc}")
    st.info(
        "Kiểm tra Aiven đang RUNNING và các thông tin Host/Port/User/Password "
        "ở DB_CONFIG. Database mặc định đang dùng là defaultdb."
    )
    st.stop()


# ============================================================
# SESSION
# ============================================================

if "selected_tour_id" not in st.session_state:
    st.session_state.selected_tour_id = None

if "last_booking" not in st.session_state:
    st.session_state.last_booking = None


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("✈️ SMART TOUR")
page = st.sidebar.radio(
    "Chức năng",
    [
        "🏠 Đặt tour",
        "🔎 Tra cứu booking",
        "📊 Quản lý dữ liệu",
    ],
)

st.sidebar.markdown("---")
st.sidebar.caption("Hệ thống đặt tour + tính giá + MySQL Aiven")


# ============================================================
# HOME / BOOKING
# ============================================================

if page == "🏠 Đặt tour":

    st.markdown(
        """
        <div class="hero">
            <h1>✈️ SMART TOUR</h1>
            <p>Hệ thống đặt tour du lịch và tính giá tự động</p>
            <p>Tour • Khách • Phòng • Khách sạn • Ăn uống • Phương tiện</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tours_df = get_tours()

    if tours_df.empty:
        st.warning("Chưa có tour đang mở.")
        st.stop()

    # --------------------------------------------------------
    # 1. CHỌN TOUR
    # --------------------------------------------------------
    st.subheader("1️⃣ Chọn tour")

    destination_options = ["Tất cả"] + sorted(
        tours_df["destination"].dropna().unique().tolist()
    )
    destination = st.selectbox("Điểm đến", destination_options)

    filtered = tours_df.copy()
    if destination != "Tất cả":
        filtered = filtered[
            filtered["destination"].astype(str) == destination
        ]

    tour_names = {
        int(r["id"]): f'{r["name"]} — {money(r["adult_price"])}/người lớn'
        for _, r in filtered.iterrows()
    }

    if not tour_names:
        st.warning("Không có tour phù hợp.")
        st.stop()

    selected_id = st.selectbox(
        "Tour",
        list(tour_names.keys()),
        format_func=lambda x: tour_names[x],
    )
    tour = get_tour(selected_id)
    st.session_state.selected_tour_id = selected_id

    st.markdown(
        f"""
        <div class="card">
            <h3>{tour['name']}</h3>
            <p><b>📍 Điểm đến:</b> {tour['destination']}</p>
            <p><b>⏱️ Thời gian:</b> {tour['duration']}</p>
            <p><b>📝 Mô tả:</b> {tour['description']}</p>
            <p><b>👤 Sức chứa:</b> tối đa {tour['max_people']} khách</p>
            <div class="price">{money(tour['adult_price'])}/người lớn</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --------------------------------------------------------
    # 2. NGÀY KHỞI HÀNH
    # --------------------------------------------------------
    st.subheader("2️⃣ Ngày khởi hành")

    min_date = date.today() + timedelta(days=1)
    departure_date = st.date_input(
        "Chọn ngày khởi hành",
        value=min_date,
        min_value=min_date,
    )

    peak = is_peak(departure_date)
    if peak:
        st.markdown(
            f'<div class="warning">🔥 Ngày này thuộc mùa cao điểm: <b>{peak["name"]}</b>. Giá phòng cao điểm sẽ được áp dụng.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="note">Ngày này đang áp dụng giá phòng thường.</div>',
            unsafe_allow_html=True,
        )

    booked = get_existing_bookings(selected_id, departure_date)
    seats_left = max(0, int(tour["available_seats"]) - booked)
    st.metric("Số chỗ còn lại theo ngày", seats_left)

    # --------------------------------------------------------
    # 3. THÔNG TIN KHÁCH
    # --------------------------------------------------------
    st.subheader("3️⃣ Thông tin người đặt")

    col1, col2 = st.columns(2)

    with col1:
        customer_name = st.text_input(
            "Họ và tên người đặt *",
            placeholder="Nguyễn Văn A",
        )

    with col2:
        customer_phone = st.text_input(
            "Số điện thoại *",
            placeholder="09xxxxxxxx",
        )

    st.markdown("### 👨‍👩‍👧‍👦 Nhập tuổi từng khách")

    guest_count = st.number_input(
        "Tổng số khách",
        min_value=1,
        max_value=min(100, int(tour["max_people"])),
        value=2,
        step=1,
    )

    guest_ages = []

    # Hiển thị theo 4 cột để nhập tuổi.
    for start in range(0, int(guest_count), 4):
        cols = st.columns(4)
        for offset, col in enumerate(cols):
            index = start + offset
            if index >= guest_count:
                break
            with col:
                age = st.number_input(
                    f"Khách {index + 1} - tuổi",
                    min_value=0,
                    max_value=120,
                    value=25 if index < 2 else 10,
                    key=f"guest_age_{index}",
                )
                guest_ages.append(int(age))

    counts = {
        "adult": sum(age_category(a) == "adult" for a in guest_ages),
        "child": sum(age_category(a) == "child" for a in guest_ages),
        "young_child": sum(age_category(a) == "young_child" for a in guest_ages),
        "infant": sum(age_category(a) == "infant" for a in guest_ages),
    }

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Người lớn", counts["adult"])
    c2.metric("Trẻ em 6–10", counts["child"])
    c3.metric("Trẻ nhỏ 2–5", counts["young_child"])
    c4.metric("Em bé 0–1", counts["infant"])

    st.caption(
        "Quy tắc mẫu: người lớn 11+ = 100%; trẻ 6–10 = giá child_price "
        "(mặc định 70%); trẻ 2–5 = 50%; em bé 0–1 = theo infant_price."
    )

    # --------------------------------------------------------
    # 4. KHÁCH SẠN + PHÒNG
    # --------------------------------------------------------
    st.subheader("4️⃣ Khách sạn và phòng")

    hotels = get_hotels(tour["destination"])

    hotel = None
    room_rate = None
    rooms = 0

    if hotels:
        hotel_options = {
            int(h["id"]): f'{h["name"]} — {h["stars"]}⭐'
            for h in hotels
        }

        hotel_id = st.selectbox(
            "Khách sạn",
            list(hotel_options.keys()),
            format_func=lambda x: hotel_options[x],
        )

        hotel = next(h for h in hotels if int(h["id"]) == hotel_id)
        room_rates = get_room_rates(hotel_id)

        if room_rates:
            room_options = {
                int(r["id"]): (
                    f'{r["room_type"]} | tối đa {r["max_guests"]} khách | '
                    f'thường {money(r["regular_price"])} | '
                    f'cao điểm {money(r["peak_price"])}'
                )
                for r in room_rates
            }

            room_id = st.selectbox(
                "Loại phòng",
                list(room_options.keys()),
                format_func=lambda x: room_options[x],
            )

            room_rate = next(
                r for r in room_rates if int(r["id"]) == room_id
            )

            auto_rooms = calculate_room_need(
                counts["adult"],
                counts["young_child"],
                counts["child"],
                counts["infant"],
                int(room_rate["max_guests"]),
            )

            rooms = st.number_input(
                "Số phòng",
                min_value=1,
                max_value=int(room_rate["inventory"]),
                value=min(auto_rooms, int(room_rate["inventory"])),
                step=1,
            )

            current_room_price = (
                room_rate["peak_price"]
                if peak
                else room_rate["regular_price"]
            )

            st.info(
                f"Giá phòng áp dụng: {money(current_room_price)}/phòng/đêm × "
                f"{rooms} phòng × {tour['nights']} đêm"
            )

            if rooms > int(room_rate["inventory"]):
                st.error("Số phòng vượt tồn kho.")
        else:
            st.warning("Khách sạn này chưa có loại phòng.")
    else:
        st.warning(
            f"Chưa có khách sạn mẫu cho {tour['destination']}. "
            "Bạn có thể thêm trong mục Quản lý dữ liệu."
        )

    # --------------------------------------------------------
    # 5. ĂN UỐNG
    # --------------------------------------------------------
    st.subheader("5️⃣ Dịch vụ ăn uống")

    meals = get_meals(tour["destination"])
    meal = None
    meal_id = None

    if meals:
        meal_options = {
            int(m["id"]): (
                f'{m["meal_type"]} - {m["name"]} - '
                f'{money(m["adult_price"])} người lớn'
            )
            for m in meals
        }

        meal_id = st.selectbox(
            "Chọn suất ăn",
            [0] + list(meal_options.keys()),
            format_func=lambda x: "Không chọn" if x == 0 else meal_options[x],
        )

        if meal_id:
            meal = next(m for m in meals if int(m["id"]) == meal_id)

    # --------------------------------------------------------
    # 6. PHƯƠNG TIỆN
    # --------------------------------------------------------
    st.subheader("6️⃣ Phương tiện")

    transports = get_transports()
    transport = None
    transport_id = None

    if transports:
        transport_options = {
            int(t["id"]): (
                f'{t["name"]} — {t["capacity"]} chỗ — '
                f'{money(t["price_per_person"])}/người'
            )
            for t in transports
        }

        transport_id = st.selectbox(
            "Phương tiện",
            [0] + list(transport_options.keys()),
            format_func=lambda x: (
                "Không chọn" if x == 0 else transport_options[x]
            ),
        )

        if transport_id:
            transport = next(
                t for t in transports if int(t["id"]) == transport_id
            )

            if int(transport["capacity"]) < len(guest_ages):
                st.warning(
                    f"Xe {transport['capacity']} chỗ không đủ cho "
                    f"{len(guest_ages)} khách."
                )

    # --------------------------------------------------------
    # 7. TÍNH GIÁ
    # --------------------------------------------------------
    st.subheader("7️⃣ Báo giá tự động")

    amounts = calculate_price(
        tour=tour,
        departure_date=departure_date,
        guest_ages=guest_ages,
        room_rate=room_rate,
        rooms=int(rooms),
        meal=meal,
        transport=transport,
    )

    st.markdown(
        f"""
        <div class="card">
            <h3>💰 Chi tiết giá</h3>
            <p>Tour: <b>{money(amounts['tour_amount'])}</b></p>
            <p>Khách sạn: <b>{money(amounts['hotel_amount'])}</b></p>
            <p>Ăn uống: <b>{money(amounts['meal_amount'])}</b></p>
            <p>Phương tiện: <b>{money(amounts['transport_amount'])}</b></p>
            <hr>
            <div class="total">TỔNG: {money(amounts['total'])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if amounts["peak"]:
        st.caption(
            f"Đã áp dụng giá phòng mùa cao điểm: {amounts['peak_name']}"
        )

    # --------------------------------------------------------
    # 8. XÁC NHẬN
    # --------------------------------------------------------
    st.subheader("8️⃣ Gửi yêu cầu đặt tour")

    note = st.text_area(
        "Ghi chú / yêu cầu đặc biệt",
        placeholder=(
            "Ví dụ: cần phòng gần nhau, có trẻ nhỏ, "
            "yêu cầu ăn chay..."
        ),
    )

    if st.button(
        "✅ ĐẶT TOUR NGAY",
        type="primary",
        use_container_width=True,
    ):
        errors = []

        if not clean(customer_name):
            errors.append("Vui lòng nhập họ tên.")

        if not clean(customer_phone):
            errors.append("Vui lòng nhập số điện thoại.")

        phone_digits = "".join(
            c for c in customer_phone if c.isdigit()
        )
        if len(phone_digits) < 9:
            errors.append("Số điện thoại chưa hợp lệ.")

        if len(guest_ages) != int(guest_count):
            errors.append("Chưa nhập đủ tuổi của tất cả khách.")

        if len(guest_ages) > seats_left:
            errors.append(
                f"Ngày này chỉ còn {seats_left} chỗ."
            )

        if room_rate and int(rooms) > int(room_rate["inventory"]):
            errors.append("Số phòng vượt tồn kho.")

        if errors:
            for e in errors:
                st.error(e)
        else:
            try:
                booking_code = create_booking(
                    customer_name=clean(customer_name),
                    customer_phone=clean(customer_phone),
                    tour_id=int(tour["id"]),
                    departure_date=departure_date,
                    guest_ages=guest_ages,
                    room_type=room_rate["room_type"] if room_rate else "",
                    rooms=int(rooms),
                    hotel_id=int(hotel["id"]) if hotel else None,
                    meal_id=int(meal_id) if meal_id else None,
                    transport_id=int(transport_id) if transport_id else None,
                    amounts=amounts,
                    note=clean(note),
                )

                st.session_state.last_booking = booking_code

                st.success(
                    f"🎉 Đặt tour thành công! Mã booking: {booking_code}"
                )

                st.info(
                    "Booking đang ở trạng thái 'Chờ xác nhận'. "
                    "Điều hành có thể kiểm tra và xác nhận trong hệ thống."
                )

                st.balloons()

            except Error as exc:
                st.error("Không thể lưu booking vào MySQL.")
                st.code(str(exc))


# ============================================================
# LOOKUP BOOKING
# ============================================================

elif page == "🔎 Tra cứu booking":

    st.title("🔎 Tra cứu booking")

    code = st.text_input(
        "Nhập mã booking",
        value=st.session_state.last_booking or "",
    ).strip()

    if st.button("Tra cứu", type="primary"):
        if not code:
            st.warning("Vui lòng nhập mã booking.")
        else:
            booking = get_booking(code)

            if not booking:
                st.error("Không tìm thấy booking.")
            else:
                st.success("Đã tìm thấy booking.")

                c1, c2, c3 = st.columns(3)
                c1.metric("Mã booking", booking["booking_code"])
                c2.metric("Trạng thái", booking["status"])
                c3.metric("Tổng tiền", money(booking["total_amount"]))

                st.markdown(
                    f"""
                    <div class="card">
                        <h3>Thông tin đặt tour</h3>
                        <p><b>Khách:</b> {booking['customer_name']}</p>
                        <p><b>SĐT:</b> {booking['customer_phone']}</p>
                        <p><b>Tour:</b> {booking['tour_name']}</p>
                        <p><b>Điểm đến:</b> {booking['destination']}</p>
                        <p><b>Ngày đi:</b> {booking['departure_date']}</p>
                        <p><b>Người lớn:</b> {booking['adults']}</p>
                        <p><b>Trẻ em 6–10:</b> {booking['children']}</p>
                        <p><b>Trẻ nhỏ 2–5:</b> {booking['young_children']}</p>
                        <p><b>Em bé 0–1:</b> {booking['infants']}</p>
                        <p><b>Khách sạn:</b> {booking['hotel_name'] or 'Không chọn'}</p>
                        <p><b>Phòng:</b> {booking['room_type'] or 'Không chọn'} ({booking['rooms']} phòng)</p>
                        <p><b>Tour:</b> {money(booking['tour_amount'])}</p>
                        <p><b>Khách sạn:</b> {money(booking['hotel_amount'])}</p>
                        <p><b>Ăn uống:</b> {money(booking['meal_amount'])}</p>
                        <p><b>Phương tiện:</b> {money(booking['transport_amount'])}</p>
                        <hr>
                        <div class="total">Tổng: {money(booking['total_amount'])}</div>
                        <p><b>Ghi chú:</b> {booking['note'] or 'Không có'}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


# ============================================================
# DATA MANAGEMENT
# ============================================================

elif page == "📊 Quản lý dữ liệu":

    st.title("📊 Quản lý dữ liệu")

    st.info(
        "Khu vực này dùng để kiểm tra dữ liệu tour/khách sạn/giá phòng/booking "
        "đang lưu trực tiếp trên MySQL Aiven."
    )

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["Tours", "Khách sạn & phòng", "Mùa cao điểm", "Booking", "SQL kiểm tra"]
    )

    with tab1:
        tours = query_df(
            """
            SELECT id,name,destination,duration,days,nights,
                   adult_price,child_price,infant_price,
                   max_people,available_seats,status
            FROM tours
            ORDER BY id
            """
        )
        st.dataframe(tours, use_container_width=True, hide_index=True)

        st.markdown("### Thêm tour mới")

        with st.form("add_tour"):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Tên tour")
                destination_new = st.text_input("Điểm đến")
                duration = st.text_input("Thời lượng", value="2 ngày 1 đêm")
                days = st.number_input("Số ngày", 1, 30, 2)
                nights = st.number_input("Số đêm", 0, 29, 1)
            with c2:
                adult_price = st.number_input("Giá người lớn", 0, 100000000, 1000000, 50000)
                child_price = st.number_input("Giá trẻ 6–10", 0, 100000000, 700000, 50000)
                infant_price = st.number_input("Giá em bé", 0, 100000000, 0, 50000)
                max_people = st.number_input("Sức chứa", 1, 500, 30)

            description = st.text_area("Mô tả")
            interests = st.text_input("Từ khóa", value="biển, nghỉ dưỡng")

            submitted = st.form_submit_button("Thêm tour")

            if submitted:
                if not name.strip() or not destination_new.strip():
                    st.error("Tên tour và điểm đến là bắt buộc.")
                else:
                    execute(
                        """
                        INSERT INTO tours
                        (name,destination,duration,days,nights,
                         adult_price,child_price,infant_price,
                         max_people,available_seats,description,interests)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            name.strip(),
                            destination_new.strip(),
                            duration.strip(),
                            int(days),
                            int(nights),
                            adult_price,
                            child_price,
                            infant_price,
                            int(max_people),
                            int(max_people),
                            description.strip(),
                            interests.strip(),
                        ),
                    )
                    st.success("Đã thêm tour.")
                    st.rerun()

    with tab2:
        hotel_df = query_df(
            """
            SELECT
                h.id,
                h.name AS hotel,
                h.destination,
                h.stars,
                r.room_type,
                r.max_guests,
                r.regular_price,
                r.peak_price,
                r.extra_adult_price,
                r.extra_child_price,
                r.inventory
            FROM hotels h
            LEFT JOIN hotel_room_rates r ON r.hotel_id=h.id
            ORDER BY h.destination,h.name,r.regular_price
            """
        )
        st.dataframe(hotel_df, use_container_width=True, hide_index=True)

        st.caption(
            "regular_price = giá thường; peak_price = giá cao điểm. "
            "Thay đổi hai cột này để hệ thống tự tính lại giá theo ngày."
        )

    with tab3:
        peak_df = query_df(
            """
            SELECT id,name,start_date,end_date,status
            FROM peak_seasons
            ORDER BY start_date
            """
        )
        st.dataframe(peak_df, use_container_width=True, hide_index=True)

    with tab4:
        booking_df = query_df(
            """
            SELECT
                b.booking_code,
                b.customer_name,
                b.customer_phone,
                t.name AS tour,
                b.departure_date,
                b.total_people,
                b.adults,
                b.children,
                b.young_children,
                b.infants,
                b.room_type,
                b.rooms,
                b.total_amount,
                b.status,
                b.created_at
            FROM bookings b
            JOIN tours t ON t.id=b.tour_id
            ORDER BY b.created_at DESC
            """
        )

        st.dataframe(
            booking_df,
            use_container_width=True,
            hide_index=True,
        )

        if not booking_df.empty:
            csv = booking_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "⬇️ Tải danh sách booking CSV",
                data=csv,
                file_name="smart_tour_bookings.csv",
                mime="text/csv",
            )

    with tab5:
        st.write("Kiểm tra kết nối:")
        try:
            row = execute("SELECT DATABASE() AS db, NOW() AS server_time", fetch="one")
            st.success("MySQL Aiven đang kết nối.")
            st.json(row)
        except Exception as exc:
            st.error(str(exc))

