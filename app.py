
import os
from datetime import date, datetime, timedelta
from decimal import Decimal

import pandas as pd
import streamlit as st
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Date, DateTime, Boolean,
    ForeignKey, Numeric, select, func, or_
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash, check_password_hash

# ============================================================
# SMART TOUR - APP ĐẶT TOUR DU LỊCH 
# Streamlit + SQLAlchemy + MySQL
# ============================================================

st.set_page_config(
    page_title="Smart Tour",
    page_icon="🌴",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.image("logo 3.jpg", use_container_width=True)

Base = declarative_base()


# ============================================================
# DATABASE MODELS
# ============================================================

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(120), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    phone = Column(String(30))
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="CUSTOMER", nullable=False)
    status = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Tour(Base):
    __tablename__ = "tours"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    destination = Column(String(120), nullable=False)
    days = Column(Integer, nullable=False)
    nights = Column(Integer, nullable=False)
    adult_price = Column(Numeric(12, 2), nullable=False)
    child_price = Column(Numeric(12, 2), nullable=False)
    description = Column(Text)
    style = Column(String(255), default="")
    image_url = Column(Text)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    departures = relationship("TourDeparture", back_populates="tour", cascade="all, delete-orphan")


class TourDeparture(Base):
    __tablename__ = "tour_departures"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False)
    departure_date = Column(Date, nullable=False)
    return_date = Column(Date, nullable=False)
    capacity = Column(Integer, default=20)
    booked_slots = Column(Integer, default=0)
    status = Column(String(20), default="OPEN")

    tour = relationship("Tour", back_populates="departures")


class Hotel(Base):
    __tablename__ = "hotels"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(180), nullable=False)
    stars = Column(Integer, default=3)
    address = Column(String(255))
    city = Column(String(120))
    phone = Column(String(30))
    description = Column(Text)
    amenities = Column(String(500))
    image_url = Column(Text)
    active = Column(Boolean, default=True)

    room_types = relationship("RoomType", back_populates="hotel", cascade="all, delete-orphan")


class RoomType(Base):
    __tablename__ = "room_types"
    id = Column(Integer, primary_key=True, autoincrement=True)
    hotel_id = Column(Integer, ForeignKey("hotels.id"), nullable=False)
    name = Column(String(120), nullable=False)
    max_adults = Column(Integer, default=2)
    max_children = Column(Integer, default=0)
    base_price = Column(Numeric(12, 2), nullable=False)
    quantity = Column(Integer, default=5)
    description = Column(Text)

    hotel = relationship("Hotel", back_populates="room_types")


class RoomPrice(Base):
    __tablename__ = "room_prices"
    id = Column(Integer, primary_key=True, autoincrement=True)
    room_type_id = Column(Integer, ForeignKey("room_types.id"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    price_per_night = Column(Numeric(12, 2), nullable=False)


class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    booking_code = Column(String(30), unique=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False)
    departure_id = Column(Integer, ForeignKey("tour_departures.id"), nullable=False)

    adults = Column(Integer, default=1)
    children = Column(Integer, default=0)
    check_in = Column(Date)
    check_out = Column(Date)
    nights = Column(Integer, default=0)

    hotel_id = Column(Integer, ForeignKey("hotels.id"))
    room_type_id = Column(Integer, ForeignKey("room_types.id"))
    room_count = Column(Integer, default=0)

    tour_total = Column(Numeric(12, 2), default=0)
    room_total = Column(Numeric(12, 2), default=0)
    service_total = Column(Numeric(12, 2), default=0)
    discount = Column(Numeric(12, 2), default=0)
    final_total = Column(Numeric(12, 2), default=0)

    status = Column(String(30), default="PENDING")
    payment_status = Column(String(30), default="UNPAID")
    created_at = Column(DateTime, default=datetime.utcnow)


class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    method = Column(String(40), default="Demo")
    status = Column(String(30), default="PAID")
    transaction_code = Column(String(80))
    paid_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db_url():
    # 1) Streamlit Cloud: [connections.mysql] or [mysql]
    try:
        if "connections" in st.secrets and "mysql" in st.secrets["connections"]:
            return st.secrets["connections"]["mysql"].get("url")
    except Exception:
        pass

    try:
        if "mysql" in st.secrets and "url" in st.secrets["mysql"]:
            return st.secrets["mysql"]["url"]
    except Exception:
        pass

    # 2) Environment variable
    return os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root:password@localhost:3306/smart_tour"
    )


@st.cache_resource
def get_engine():
    url = get_db_url()
    if not url:
        raise RuntimeError("Chưa cấu hình DATABASE_URL / st.secrets.")
    return create_engine(url, pool_pre_ping=True, pool_recycle=280)


@st.cache_resource
def get_session_factory():
    engine = get_engine()
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def db_session():
    return get_session_factory()()


# ============================================================
# HELPERS
# ============================================================

def money(value):
    if value is None:
        return "0 đ"
    return f"{int(Decimal(str(value))):,} đ".replace(",", ".")


def money_number(value):
    return Decimal(str(value or 0))


def days_nights(check_in, check_out):
    nights = (check_out - check_in).days
    return nights + 1, nights


def get_room_price(session, room_type_id, target_date):
    room = session.get(RoomType, room_type_id)
    if not room:
        return Decimal("0")

    special = session.execute(
        select(RoomPrice)
        .where(
            RoomPrice.room_type_id == room_type_id,
            RoomPrice.start_date <= target_date,
            RoomPrice.end_date >= target_date,
        )
    ).scalars().first()

    if special:
        return money_number(special.price_per_night)

    return money_number(room.base_price)


def calculate_room_total(session, room_type_id, check_in, check_out, room_count):
    total = Decimal("0")
    current = check_in
    while current < check_out:
        total += get_room_price(session, room_type_id, current)
        current += timedelta(days=1)
    return total * room_count


def availability(session, room_type_id, check_in, check_out):
    room = session.get(RoomType, room_type_id)
    if not room:
        return 0

    overlapping = session.execute(
        select(Booking).where(
            Booking.room_type_id == room_type_id,
            Booking.check_in < check_out,
            Booking.check_out > check_in,
            Booking.status.in_(["PENDING", "CONFIRMED", "PAID"]),
        )
    ).scalars().all()

    used = sum(int(b.room_count or 0) for b in overlapping)
    return max(0, int(room.quantity) - used)


def booking_code():
    return "ST" + datetime.now().strftime("%y%m%d%H%M%S%f")[-10:]


def seed_data():
    session = db_session()
    try:
        admin = session.execute(
            select(User).where(User.email == "admin@smarttour.vn")
        ).scalars().first()

        if not admin:
            session.add(User(
                full_name="Quản trị viên",
                email="admin@smarttour.vn",
                phone="0900000000",
                password_hash=generate_password_hash("admin123"),
                role="ADMIN",
            ))

        if session.execute(select(Tour)).scalars().first() is None:
            tours = [
                Tour(
                    name="Vũng Tàu 3N2Đ - Biển & Nghỉ dưỡng",
                    destination="Vũng Tàu",
                    days=3, nights=2,
                    adult_price=Decimal("1500000"),
                    child_price=Decimal("1050000"),
                    description="Khám phá biển, Bạch Dinh, Mũi Nghinh Phong và ẩm thực địa phương.",
                    style="Nghỉ dưỡng, Biển, Ẩm thực, Check-in",
                    image_url="https://images.unsplash.com/photo-1590479773265-7464e5d48118?auto=format&fit=crop&w=1200&q=80",
                ),
                Tour(
                    name="Đà Lạt 3N2Đ - Chill & Check-in",
                    destination="Đà Lạt",
                    days=3, nights=2,
                    adult_price=Decimal("2000000"),
                    child_price=Decimal("1400000"),
                    description="Không gian mát mẻ, cà phê, cảnh quan và các điểm check-in nổi bật.",
                    style="Check-in, Nghỉ dưỡng, Khám phá, Ẩm thực",
                    image_url="https://images.unsplash.com/photo-1555921015-5532091f6026?auto=format&fit=crop&w=1200&q=80",
                ),
                Tour(
                    name="Nha Trang 4N3Đ - Biển & Khám phá",
                    destination="Nha Trang",
                    days=4, nights=3,
                    adult_price=Decimal("2500000"),
                    child_price=Decimal("1750000"),
                    description="Biển xanh, đảo, hải sản và trải nghiệm nghỉ dưỡng.",
                    style="Biển, Khám phá, Nghỉ dưỡng, Ẩm thực",
                    image_url="https://images.unsplash.com/photo-1559592413-7cec4d0cae2b?auto=format&fit=crop&w=1200&q=80",
                ),
            ]
            session.add_all(tours)
            session.flush()

            for tour in tours:
                start = date.today() + timedelta(days=7)
                for i in range(6):
                    d = start + timedelta(days=i * 7)
                    session.add(TourDeparture(
                        tour_id=tour.id,
                        departure_date=d,
                        return_date=d + timedelta(days=tour.days - 1),
                        capacity=30,
                        booked_slots=0,
                        status="OPEN",
                    ))

        if session.execute(select(Hotel)).scalars().first() is None:
            hotels = [
                Hotel(
                    name="Sea Pearl Hotel",
                    stars=3,
                    address="Trung tâm Vũng Tàu",
                    city="Vũng Tàu",
                    phone="0254 123 4567",
                    description="Khách sạn gần biển, phù hợp nghỉ dưỡng và đi theo gia đình.",
                    amenities="WiFi, Hồ bơi, Bữa sáng, Điều hòa, Bãi đỗ xe",
                    image_url="https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=1200&q=80",
                ),
                Hotel(
                    name="Green Hill Resort",
                    stars=4,
                    address="Khu nghỉ dưỡng Đà Lạt",
                    city="Đà Lạt",
                    phone="0263 234 5678",
                    description="Không gian yên tĩnh, phù hợp nghỉ dưỡng và check-in.",
                    amenities="WiFi, Nhà hàng, Hồ bơi, Spa, Bữa sáng",
                    image_url="https://images.unsplash.com/photo-1564501049412-61c2a3083791?auto=format&fit=crop&w=1200&q=80",
                ),
                Hotel(
                    name="Ocean View Hotel",
                    stars=4,
                    address="Trung tâm Nha Trang",
                    city="Nha Trang",
                    phone="0258 345 6789",
                    description="Khách sạn gần biển, phòng có nhiều lựa chọn.",
                    amenities="WiFi, View biển, Nhà hàng, Hồ bơi, Bữa sáng",
                    image_url="https://images.unsplash.com/photo-1566665797739-1674de7a421a?auto=format&fit=crop&w=1200&q=80",
                ),
            ]
            session.add_all(hotels)
            session.flush()

            room_templates = [
                ("Standard", 2, 1, Decimal("600000"), 8),
                ("Deluxe", 2, 1, Decimal("800000"), 6),
                ("Family", 4, 2, Decimal("1200000"), 4),
            ]
            for hotel in hotels:
                for name, adults, children, price, quantity in room_templates:
                    session.add(RoomType(
                        hotel_id=hotel.id,
                        name=name,
                        max_adults=adults,
                        max_children=children,
                        base_price=price,
                        quantity=quantity,
                        description=f"Phòng {name} tiện nghi, phù hợp khách du lịch.",
                    ))

        session.commit()
    finally:
        session.close()


def current_user():
    return st.session_state.get("user")


def logout():
    for key in ["user", "page"]:
        st.session_state.pop(key, None)
    st.rerun()


def login_user(user):
    st.session_state.user = {
        "id": user.id,
        "name": user.full_name,
        "email": user.email,
        "role": user.role,
    }
    st.session_state.page = "home"


# ============================================================
# UI CSS
# ============================================================

st.markdown("""
<style>
.main-title {
    font-size: 42px;
    font-weight: 800;
    margin-bottom: 0;
}
.subtitle {
    color: #64748b;
    font-size: 17px;
}
.card {
    border: 1px solid #e5e7eb;
    border-radius: 18px;
    padding: 18px;
    background: white;
    margin-bottom: 14px;
}
.metric-card {
    border-radius: 18px;
    padding: 18px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
}
.price {
    font-size: 24px;
    font-weight: 800;
}
.small {
    color: #64748b;
    font-size: 14px;
}
</style>
""", unsafe_allow_html=True)


# ============================================================
# STARTUP
# ============================================================

try:
    seed_data()
except Exception as e:
    st.error("Không thể kết nối MySQL hoặc tạo dữ liệu.")
    st.code(str(e))
    st.info("Hãy kiểm tra DATABASE_URL hoặc st.secrets['mysql']['url'].")
    st.stop()


# ============================================================
# LOGIN / REGISTER
# ============================================================

def login_page():
    st.markdown('<p class="main-title">🌴 Smart Tour</p>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Đặt tour theo ngân sách và sở thích của bạn.</p>', unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["🔐 Đăng nhập", "📝 Đăng ký"])

    with tab1:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Mật khẩu", type="password")
            submitted = st.form_submit_button("Đăng nhập", use_container_width=True)

        if submitted:
            session = db_session()
            try:
                user = session.execute(
                    select(User).where(User.email == email.strip().lower())
                ).scalars().first()

                if user and user.status and check_password_hash(user.password_hash, password):
                    login_user(user)
                    st.success("Đăng nhập thành công!")
                    st.rerun()
                else:
                    st.error("Email hoặc mật khẩu không đúng.")
            finally:
                session.close()

    with tab2:
        with st.form("register_form"):
            name = st.text_input("Họ và tên")
            email = st.text_input("Email", key="register_email")
            phone = st.text_input("Số điện thoại")
            password = st.text_input("Mật khẩu", type="password", key="register_password")
            password2 = st.text_input("Nhập lại mật khẩu", type="password")
            submitted = st.form_submit_button("Tạo tài khoản", use_container_width=True)

        if submitted:
            if not name.strip() or not email.strip() or not password:
                st.error("Vui lòng nhập đầy đủ thông tin.")
            elif password != password2:
                st.error("Mật khẩu nhập lại không khớp.")
            else:
                session = db_session()
                try:
                    exists = session.execute(
                        select(User).where(User.email == email.strip().lower())
                    ).scalars().first()
                    if exists:
                        st.error("Email này đã tồn tại.")
                    else:
                        user = User(
                            full_name=name.strip(),
                            email=email.strip().lower(),
                            phone=phone.strip(),
                            password_hash=generate_password_hash(password),
                            role="CUSTOMER",
                        )
                        session.add(user)
                        session.commit()
                        st.success("Đăng ký thành công. Bạn có thể đăng nhập.")
                finally:
                    session.close()


# ============================================================
# CUSTOMER PAGES
# ============================================================

def customer_sidebar():
    with st.sidebar:
        st.markdown("## 🌴 Smart Tour")
        st.write(f"Xin chào, **{current_user()['name']}**")

        pages = {
            "🏠 Trang chủ": "home",
            "✨ Tạo chuyến đi": "smart",
            "🧳 Khám phá tour": "tours",
            "📋 Đơn của tôi": "bookings",
            "👤 Tài khoản": "profile",
        }
        for label, page in pages.items():
            if st.button(label, use_container_width=True):
                st.session_state.page = page
                st.rerun()

        st.divider()
        if st.button("🚪 Đăng xuất", use_container_width=True):
            logout()


def home_page():
    st.markdown('<p class="main-title">🌴 Smart Tour</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="subtitle">Chọn điểm đến, ngân sách và phong cách — hệ thống sẽ giúp bạn tạo chuyến đi phù hợp.</p>',
        unsafe_allow_html=True
    )

    st.image(
        "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1800&q=85",
        use_container_width=True,
    )

    st.markdown("## ✨ Tạo chuyến đi thông minh")
    c1, c2, c3 = st.columns(3)
    c1.info("🎯 Cá nhân hóa theo sở thích")
    c2.info("💰 Kiểm soát ngân sách")
    c3.info("🏨 Tự tính tiền phòng theo số đêm")

    if st.button("🚀 Bắt đầu tạo chuyến đi", type="primary", use_container_width=True):
        st.session_state.page = "smart"
        st.rerun()


def smart_page():
    st.title("✨ Smart Tour Generator")
    st.caption("Nhập nhu cầu của bạn. Hệ thống sẽ chấm điểm tour và đề xuất phương án phù hợp.")

    session = db_session()
    try:
        tours = session.execute(
            select(Tour).where(Tour.active == True)
        ).scalars().all()
        hotels = session.execute(
            select(Hotel).where(Hotel.active == True)
        ).scalars().all()

        if not tours:
            st.warning("Chưa có tour.")
            return

        destinations = sorted({t.destination for t in tours})
        destination = st.selectbox("📍 Điểm đến", destinations)

        c1, c2, c3 = st.columns(3)
        with c1:
            start = st.date_input("📅 Ngày khởi hành", min_value=date.today())
        with c2:
            adults = st.number_input("👨 Người lớn", min_value=1, max_value=30, value=2)
        with c3:
            children = st.number_input("👧 Trẻ em", min_value=0, max_value=20, value=0)

        budget = st.number_input(
            "💰 Ngân sách dự kiến (VNĐ)",
            min_value=500000,
            value=5000000,
            step=500000,
        )

        styles = ["🏖️ Nghỉ dưỡng", "📸 Check-in", "🍜 Ẩm thực", "🌲 Khám phá", "💰 Tiết kiệm"]
        selected_styles = st.multiselect(
            "❤️ Bạn thích phong cách nào?",
            styles,
            default=["🏖️ Nghỉ dưỡng"],
        )

        if st.button("✨ TẠO CHUYẾN ĐI", type="primary", use_container_width=True):
            candidates = [t for t in tours if t.destination == destination]
            selected = []

            style_words = [x.split(" ", 1)[-1] for x in selected_styles]

            for tour in candidates:
                score = 0
                tour_styles = (tour.style or "").lower()
                for word in style_words:
                    if word.lower() in tour_styles:
                        score += 2

                estimated = money_number(tour.adult_price) * adults + money_number(tour.child_price) * children

                if estimated <= budget:
                    score += 3
                elif estimated <= budget * Decimal("1.15"):
                    score += 1

                score -= abs(tour.days - 3) * 0.2
                selected.append((score, tour, estimated))

            selected.sort(key=lambda x: x[0], reverse=True)

            if not selected:
                st.warning("Không tìm thấy tour phù hợp.")
                return

            _, tour, tour_estimated = selected[0]
            check_in = start
            check_out = start + timedelta(days=tour.nights)

            departures = [
                d for d in tour.departures
                if d.departure_date == start and d.status == "OPEN"
            ]

            if not departures:
                departures = [
                    d for d in tour.departures
                    if d.departure_date >= start and d.status == "OPEN"
                ]

            departure = departures[0] if departures else None

            hotel_options = [h for h in hotels if h.city == destination]
            if not hotel_options:
                hotel_options = hotels

            hotel = min(
                hotel_options,
                key=lambda h: min([money_number(r.base_price) for r in h.room_types] or [Decimal("999999999")])
            )

            suitable_rooms = [
                r for r in hotel.room_types
                if r.max_adults >= min(adults, r.max_adults)
            ]

            if not suitable_rooms:
                suitable_rooms = hotel.room_types

            room = min(
                suitable_rooms,
                key=lambda r: money_number(r.base_price)
            )

            required_rooms = max(
                1,
                (adults + children + room.max_adults - 1) // room.max_adults
            )

            available = availability(session, room.id, check_in, check_out)
            required_rooms = min(required_rooms, max(1, available)) if available else required_rooms

            room_total = calculate_room_total(
                session, room.id, check_in, check_out, required_rooms
            )

            tour_total = (
                money_number(tour.adult_price) * adults
                + money_number(tour.child_price) * children
            )

            total = tour_total + room_total
            difference = Decimal(str(budget)) - total

            st.divider()
            st.subheader("🎯 Chuyến đi được thiết kế cho bạn")

            st.image(tour.image_url, use_container_width=True)
            st.markdown(f"## {tour.name}")
            st.write(tour.description)

            a, b, c, d = st.columns(4)
            a.metric("Thời gian", f"{tour.days} ngày {tour.nights} đêm")
            b.metric("Khách", f"{adults + children} người")
            c.metric("Khách sạn", f"{hotel.stars} ⭐")
            d.metric("Phòng", f"{required_rooms} phòng")

            st.markdown("### 🗓️ Lịch trình gợi ý")
            itinerary = [
                ("Ngày 1", f"🚌 Khởi hành → {destination} → nhận phòng → tham quan nhẹ → ăn tối"),
                ("Ngày 2", "☀️ Ăn sáng → điểm tham quan chính → trải nghiệm ẩm thực → tự do"),
                ("Ngày 3", "📸 Check-in → mua đặc sản → trả phòng → trở về"),
            ]
            for day, text in itinerary[:tour.days]:
                st.markdown(f"**{day}:** {text}")

            st.markdown("### 💰 Phân bổ chi phí")
            cost_df = pd.DataFrame({
                "Hạng mục": ["Tour", "Khách sạn", "Tổng"],
                "Số tiền": [int(tour_total), int(room_total), int(total)]
            })
            st.dataframe(
                cost_df,
                hide_index=True,
                use_container_width=True,
                column_config={"Số tiền": st.column_config.NumberColumn(format="%d đ")}
            )

            if difference >= 0:
                st.success(f"💚 Trong ngân sách. Bạn còn khoảng **{money(difference)}**.")
            else:
                st.warning(f"⚠️ Đang vượt ngân sách **{money(abs(difference))}**.")

                cheaper_rooms = [
                    r for r in hotel.room_types
                    if money_number(r.base_price) < money_number(room.base_price)
                ]
                if cheaper_rooms:
                    cheaper = min(cheaper_rooms, key=lambda r: money_number(r.base_price))
                    cheaper_total = calculate_room_total(
                        session, cheaper.id, check_in, check_out, required_rooms
                    )
                    new_total = tour_total + cheaper_total
                    saved = total - new_total

                    st.info(
                        f"💡 Gợi ý tiết kiệm: đổi **{room.name}** sang **{cheaper.name}** "
                        f"để tiết kiệm khoảng **{money(saved)}**."
                    )

            if departure:
                st.caption(
                    f"Ngày khởi hành phù hợp: {departure.departure_date.strftime('%d/%m/%Y')} "
                    f"→ {departure.return_date.strftime('%d/%m/%Y')}"
                )

            if st.button("🧳 Đặt chuyến đi này", type="primary"):
                if not departure:
                    st.error("Chưa có lịch khởi hành phù hợp.")
                elif departure.booked_slots + adults + children > departure.capacity:
                    st.error("Lịch khởi hành đã gần đầy.")
                elif available < required_rooms:
                    st.error(f"Loại phòng {room.name} chỉ còn {available} phòng.")
                else:
                    st.session_state.booking_draft = {
                        "tour_id": tour.id,
                        "departure_id": departure.id,
                        "hotel_id": hotel.id,
                        "room_type_id": room.id,
                        "check_in": check_in,
                        "check_out": check_out,
                        "nights": tour.nights,
                        "adults": adults,
                        "children": children,
                        "room_count": required_rooms,
                        "tour_total": tour_total,
                        "room_total": room_total,
                        "final_total": total,
                    }
                    st.session_state.page = "confirm"
                    st.rerun()
    finally:
        session.close()


def tours_page():
    st.title("🧳 Khám phá tour")
    session = db_session()
    try:
        tours = session.execute(select(Tour).where(Tour.active == True)).scalars().all()

        cols = st.columns(3)
        for i, tour in enumerate(tours):
            with cols[i % 3]:
                st.image(tour.image_url, use_container_width=True)
                st.subheader(tour.name)
                st.caption(f"{tour.destination} • {tour.days}N{tour.nights}Đ")
                st.write(tour.description)
                st.markdown(f"### {money(tour.adult_price)}/người")
                st.caption(f"Phong cách: {tour.style}")
    finally:
        session.close()


def confirm_page():
    st.title("🧾 Xác nhận đặt tour")
    draft = st.session_state.get("booking_draft")

    if not draft:
        st.warning("Chưa có thông tin đặt tour.")
        return

    session = db_session()
    try:
        tour = session.get(Tour, draft["tour_id"])
        hotel = session.get(Hotel, draft["hotel_id"])
        room = session.get(RoomType, draft["room_type_id"])
        departure = session.get(TourDeparture, draft["departure_id"])

        st.image(tour.image_url, use_container_width=True)
        st.subheader(tour.name)

        c1, c2, c3 = st.columns(3)
        c1.write(f"📅 {draft['check_in'].strftime('%d/%m/%Y')} → {draft['check_out'].strftime('%d/%m/%Y')}")
        c2.write(f"👥 {draft['adults']} người lớn + {draft['children']} trẻ em")
        c3.write(f"🏨 {hotel.name} • {room.name} × {draft['room_count']}")

        st.divider()
        st.write(f"Tiền tour: **{money(draft['tour_total'])}**")
        st.write(f"Tiền phòng: **{money(draft['room_total'])}**")
        st.markdown(f"## Tổng: {money(draft['final_total'])}")

        st.warning("Đây là phiên bản demo. Nút thanh toán bên dưới chỉ mô phỏng thanh toán.")

        if st.button("💳 Xác nhận & thanh toán demo", type="primary", use_container_width=True):
            # Recheck room availability before creating booking
            available = availability(
                session,
                room.id,
                draft["check_in"],
                draft["check_out"],
            )
            if available < draft["room_count"]:
                st.error(f"Phòng không còn đủ. Hiện còn {available} phòng.")
                return

            booking = Booking(
                booking_code=booking_code(),
                customer_id=current_user()["id"],
                tour_id=tour.id,
                departure_id=departure.id,
                adults=draft["adults"],
                children=draft["children"],
                check_in=draft["check_in"],
                check_out=draft["check_out"],
                nights=draft["nights"],
                hotel_id=hotel.id,
                room_type_id=room.id,
                room_count=draft["room_count"],
                tour_total=draft["tour_total"],
                room_total=draft["room_total"],
                service_total=0,
                discount=0,
                final_total=draft["final_total"],
                status="CONFIRMED",
                payment_status="PAID",
            )
            session.add(booking)
            session.flush()

            departure.booked_slots = int(departure.booked_slots or 0) + draft["adults"] + draft["children"]

            session.add(Payment(
                booking_id=booking.id,
                amount=draft["final_total"],
                method="Demo",
                status="PAID",
                transaction_code="DEMO-" + booking.booking_code,
            ))

            session.commit()

            st.session_state.booking_success = booking.booking_code
            st.session_state.pop("booking_draft", None)
            st.session_state.page = "bookings"
            st.success(f"Đặt tour thành công! Mã đơn: {booking.booking_code}")
            st.rerun()
    finally:
        session.close()


def bookings_page():
    st.title("📋 Đơn của tôi")
    session = db_session()
    try:
        bookings = session.execute(
            select(Booking)
            .where(Booking.customer_id == current_user()["id"])
            .order_by(Booking.created_at.desc())
        ).scalars().all()

        if not bookings:
            st.info("Bạn chưa có đơn đặt tour.")
            return

        for b in bookings:
            tour = session.get(Tour, b.tour_id)
            hotel = session.get(Hotel, b.hotel_id) if b.hotel_id else None
            room = session.get(RoomType, b.room_type_id) if b.room_type_id else None

            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 2, 1])
                with c1:
                    st.subheader(tour.name if tour else "Tour")
                    st.write(f"Mã đơn: **{b.booking_code}**")
                    st.write(f"📅 {b.check_in.strftime('%d/%m/%Y')} → {b.check_out.strftime('%d/%m/%Y')}")
                with c2:
                    st.write(f"🏨 {hotel.name if hotel else '-'}")
                    st.write(f"🛏️ {room.name if room else '-'} × {b.room_count}")
                    st.write(f"👥 {b.adults} người lớn + {b.children} trẻ em")
                with c3:
                    st.metric("Tổng", money(b.final_total))
                    st.success(b.status)
                    st.caption(b.payment_status)
    finally:
        session.close()


def profile_page():
    st.title("👤 Tài khoản")
    st.write(f"**Họ tên:** {current_user()['name']}")
    st.write(f"**Email:** {current_user()['email']}")
    st.write(f"**Vai trò:** {current_user()['role']}")


# ============================================================
# ADMIN
# ============================================================

def admin_sidebar():
    with st.sidebar:
        st.markdown("## 🔐 Admin Smart Tour")
        st.write(f"Xin chào, **{current_user()['name']}**")

        pages = {
            "📊 Dashboard": "admin_dashboard",
            "🧳 Quản lý tour": "admin_tours",
            "🏨 Quản lý khách sạn": "admin_hotels",
            "📋 Quản lý booking": "admin_bookings",
            "👥 Khách hàng": "admin_customers",
        }

        for label, page in pages.items():
            if st.button(label, use_container_width=True):
                st.session_state.page = page
                st.rerun()

        st.divider()
        if st.button("🚪 Đăng xuất", use_container_width=True):
            logout()


def admin_dashboard():
    st.title("📊 Admin Dashboard")
    session = db_session()
    try:
        customer_count = session.scalar(
            select(func.count(User.id)).where(User.role == "CUSTOMER")
        ) or 0
        tour_count = session.scalar(
            select(func.count(Tour.id)).where(Tour.active == True)
        ) or 0
        hotel_count = session.scalar(
            select(func.count(Hotel.id)).where(Hotel.active == True)
        ) or 0
        booking_count = session.scalar(select(func.count(Booking.id))) or 0
        revenue = session.scalar(
            select(func.coalesce(func.sum(Booking.final_total), 0))
            .where(Booking.payment_status == "PAID")
        ) or 0

        a, b, c, d, e = st.columns(5)
        a.metric("👥 Khách hàng", customer_count)
        b.metric("🧳 Tour", tour_count)
        c.metric("🏨 Khách sạn", hotel_count)
        d.metric("📋 Booking", booking_count)
        e.metric("💰 Doanh thu", money(revenue))

        st.subheader("⚠️ Việc cần xử lý")

        pending = session.scalar(
            select(func.count(Booking.id)).where(Booking.status == "PENDING")
        ) or 0

        low_departures = session.execute(
            select(TourDeparture, Tour)
            .join(Tour, Tour.id == TourDeparture.tour_id)
            .where(TourDeparture.capacity - TourDeparture.booked_slots <= 3)
        ).all()

        if pending:
            st.warning(f"🟠 Có {pending} booking đang chờ xác nhận.")

        if low_departures:
            for dep, tour in low_departures[:5]:
                remaining = dep.capacity - dep.booked_slots
                st.warning(
                    f"⚠️ {tour.name} ngày {dep.departure_date.strftime('%d/%m/%Y')} "
                    f"còn {remaining} chỗ."
                )

        bookings = session.execute(
            select(Booking).order_by(Booking.created_at.desc()).limit(10)
        ).scalars().all()

        st.subheader("📋 Booking mới nhất")
        rows = []
        for b in bookings:
            tour = session.get(Tour, b.tour_id)
            user = session.get(User, b.customer_id)
            rows.append({
                "Mã": b.booking_code,
                "Khách": user.full_name if user else "",
                "Tour": tour.name if tour else "",
                "Tổng tiền": int(b.final_total or 0),
                "Trạng thái": b.status,
                "Thanh toán": b.payment_status,
            })

        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    finally:
        session.close()


def admin_tours():
    st.title("🧳 Quản lý tour")
    session = db_session()
    try:
        with st.expander("➕ Thêm tour mới"):
            with st.form("new_tour"):
                name = st.text_input("Tên tour")
                destination = st.text_input("Điểm đến")
                days = st.number_input("Số ngày", min_value=1, value=3)
                nights = st.number_input("Số đêm", min_value=0, value=2)
                adult = st.number_input("Giá người lớn", min_value=0, value=1500000, step=100000)
                child = st.number_input("Giá trẻ em", min_value=0, value=1050000, step=100000)
                style = st.text_input("Phong cách", value="Nghỉ dưỡng, Biển")
                image = st.text_input("URL ảnh")
                desc = st.text_area("Mô tả")
                save = st.form_submit_button("Lưu tour")

            if save:
                if not name or not destination:
                    st.error("Vui lòng nhập tên và điểm đến.")
                else:
                    session.add(Tour(
                        name=name,
                        destination=destination,
                        days=days,
                        nights=nights,
                        adult_price=adult,
                        child_price=child,
                        style=style,
                        image_url=image,
                        description=desc,
                    ))
                    session.commit()
                    st.success("Đã thêm tour.")
                    st.rerun()

        tours = session.execute(select(Tour).order_by(Tour.id.desc())).scalars().all()
        for tour in tours:
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 1])
                with c1:
                    st.subheader(tour.name)
                    st.write(f"{tour.destination} • {tour.days}N{tour.nights}Đ")
                with c2:
                    st.write(f"Người lớn: {money(tour.adult_price)}")
                    st.write(f"Trẻ em: {money(tour.child_price)}")
                with c3:
                    st.write("🟢 Hoạt động" if tour.active else "🔴 Tắt")
    finally:
        session.close()


def admin_hotels():
    st.title("🏨 Quản lý khách sạn")
    session = db_session()
    try:
        with st.expander("➕ Thêm khách sạn"):
            with st.form("new_hotel"):
                name = st.text_input("Tên khách sạn")
                city = st.text_input("Thành phố")
                stars = st.number_input("Số sao", min_value=1, max_value=5, value=3)
                address = st.text_input("Địa chỉ")
                phone = st.text_input("Điện thoại")
                amenities = st.text_input("Tiện nghi")
                image = st.text_input("URL ảnh")
                desc = st.text_area("Mô tả")
                save = st.form_submit_button("Lưu khách sạn")

            if save:
                if not name or not city:
                    st.error("Vui lòng nhập tên và thành phố.")
                else:
                    session.add(Hotel(
                        name=name,
                        city=city,
                        stars=stars,
                        address=address,
                        phone=phone,
                        amenities=amenities,
                        image_url=image,
                        description=desc,
                    ))
                    session.commit()
                    st.success("Đã thêm khách sạn.")
                    st.rerun()

        hotels = session.execute(select(Hotel).order_by(Hotel.id.desc())).scalars().all()
        for hotel in hotels:
            with st.container(border=True):
                st.subheader(f"{hotel.name} {'⭐' * hotel.stars}")
                st.write(f"📍 {hotel.address or hotel.city}")
                st.write(f"☎️ {hotel.phone or '-'}")
                st.write(f"✨ {hotel.amenities or '-'}")

                rooms = hotel.room_types
                if rooms:
                    room_rows = [
                        {
                            "Loại phòng": r.name,
                            "Sức chứa": f"{r.max_adults} NL + {r.max_children} TE",
                            "Giá/đêm": int(r.base_price),
                            "Số phòng": r.quantity,
                        }
                        for r in rooms
                    ]
                    st.dataframe(pd.DataFrame(room_rows), hide_index=True, use_container_width=True)
    finally:
        session.close()


def admin_bookings():
    st.title("📋 Quản lý booking")
    session = db_session()
    try:
        bookings = session.execute(
            select(Booking).order_by(Booking.created_at.desc())
        ).scalars().all()

        if not bookings:
            st.info("Chưa có booking.")
            return

        for b in bookings:
            user = session.get(User, b.customer_id)
            tour = session.get(Tour, b.tour_id)

            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 3, 2])
                with c1:
                    st.subheader(b.booking_code)
                    st.write(user.full_name if user else "-")
                with c2:
                    st.write(tour.name if tour else "-")
                    st.write(f"{b.check_in} → {b.check_out}")
                    st.write(f"Tổng: **{money(b.final_total)}**")
                with c3:
                    new_status = st.selectbox(
                        "Trạng thái",
                        ["PENDING", "CONFIRMED", "PAID", "COMPLETED", "CANCELLED"],
                        index=["PENDING", "CONFIRMED", "PAID", "COMPLETED", "CANCELLED"].index(b.status)
                        if b.status in ["PENDING", "CONFIRMED", "PAID", "COMPLETED", "CANCELLED"] else 0,
                        key=f"status_{b.id}",
                    )
                    if st.button("💾 Cập nhật", key=f"update_{b.id}"):
                        b.status = new_status
                        if new_status == "PAID":
                            b.payment_status = "PAID"
                        session.commit()
                        st.success("Đã cập nhật.")
                        st.rerun()
    finally:
        session.close()


def admin_customers():
    st.title("👥 Khách hàng")
    session = db_session()
    try:
        users = session.execute(
            select(User).where(User.role == "CUSTOMER").order_by(User.created_at.desc())
        ).scalars().all()

        rows = []
        for u in users:
            booking_count = session.scalar(
                select(func.count(Booking.id)).where(Booking.customer_id == u.id)
            ) or 0
            total = session.scalar(
                select(func.coalesce(func.sum(Booking.final_total), 0))
                .where(Booking.customer_id == u.id)
            ) or 0
            rows.append({
                "Họ tên": u.full_name,
                "Email": u.email,
                "SĐT": u.phone,
                "Số booking": booking_count,
                "Tổng giá trị": int(total),
                "Trạng thái": "Hoạt động" if u.status else "Khóa",
            })

        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    finally:
        session.close()


# ============================================================
# ROUTER
# ============================================================

if not current_user():
    login_page()
else:
    if current_user()["role"] == "ADMIN":
        admin_sidebar()
        page = st.session_state.get("page", "admin_dashboard")

        if page == "admin_tours":
            admin_tours()
        elif page == "admin_hotels":
            admin_hotels()
        elif page == "admin_bookings":
            admin_bookings()
        elif page == "admin_customers":
            admin_customers()
        else:
            admin_dashboard()
    else:
        customer_sidebar()
        page = st.session_state.get("page", "home")

        if page == "smart":
            smart_page()
        elif page == "tours":
            tours_page()
        elif page == "confirm":
            confirm_page()
        elif page == "bookings":
            bookings_page()
        elif page == "profile":
            profile_page()
        else:
            home_page()

