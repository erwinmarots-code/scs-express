from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='admin')  # admin, kurir, petugas

class Pelanggan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipe = db.Column(db.String(10))
    nama = db.Column(db.String(100), nullable=False)
    perusahaan = db.Column(db.String(100))
    alamat = db.Column(db.Text)
    no_telp = db.Column(db.String(20))
    kode_kota = db.Column(db.String(10))

class Pengiriman(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nomor_resi = db.Column(db.String(50), unique=True, index=True)
    barcode_image = db.Column(db.String(100))
    kota_asal = db.Column(db.String(50))
    kota_tujuan = db.Column(db.String(50))
    tgl_pickup = db.Column(db.Date)
    petugas_pickup = db.Column(db.String(100))
    pengirim_id = db.Column(db.Integer, db.ForeignKey('pelanggan.id'))
    penerima_id = db.Column(db.Integer, db.ForeignKey('pelanggan.id'))
    jenis_service = db.Column(db.String(10))
    jenis_barang = db.Column(db.String(10))
    jumlah_koli = db.Column(db.Integer)
    berat_kg = db.Column(db.Float)
    tarif_per_kg = db.Column(db.Float)
    ppn = db.Column(db.Float, default=0.0)
    asuransi = db.Column(db.Float, default=0.0)
    biaya_packing = db.Column(db.Float, default=0.0)
    total_biaya = db.Column(db.Float)
    metode_pembayaran = db.Column(db.String(10))
    keterangan = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')
    verified = db.Column(db.Boolean, default=False)
    retur_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    pengirim = db.relationship('Pelanggan', foreign_keys=[pengirim_id])
    penerima = db.relationship('Pelanggan', foreign_keys=[penerima_id])

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True, default=1)
    print_method = db.Column(db.String(10), default='browser')
    resi_prefix = db.Column(db.String(10), default='')
    resi_date_format = db.Column(db.String(20), default='%Y%m%d')
    resi_counter_length = db.Column(db.Integer, default=4)
    resi_last_number = db.Column(db.Integer, default=0)
    company_address = db.Column(db.String(200), default='')
    company_phone = db.Column(db.String(30), default='')

    @staticmethod
    def get():
        settings = Settings.query.get(1)
        if not settings:
            settings = Settings(id=1)
            db.session.add(settings)
            db.session.commit()
        return settings

class BiayaOperasional(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tanggal = db.Column(db.Date, nullable=False)
    jenis = db.Column(db.String(10), default='')
    keterangan = db.Column(db.String(200))
    jumlah = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)