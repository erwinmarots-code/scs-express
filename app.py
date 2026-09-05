import os
from io import BytesIO
import calendar
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, redirect, url_for, flash, request, send_file, make_response, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User, Pelanggan, Pengiriman, Settings, BiayaOperasional
from forms import (
    LoginForm, InputBarangForm, PelangganForm, SettingsForm,
    ChangePasswordForm, BiayaOperasionalForm
)
from utils import (
    generate_resi_number, generate_barcode, hitung_total,
    export_to_excel, import_from_excel, import_biaya_from_excel
)
from sqlalchemy import extract, func, or_
import pandas as pd

app = Flask(__name__)
app.config['SECRET_KEY'] = 'rahasia-super-kuat'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['UPLOAD_FOLDER'] = 'uploads'
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------- DECORATOR ROLE ----------
def role_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if current_user.role not in roles:
                flash('Anda tidak memiliki akses ke halaman ini.')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ---------- CONTEXT PROCESSOR ----------
@app.context_processor
def inject_settings():
    return dict(get_settings=Settings.get)

# ---------- INISIALISASI DATABASE ----------
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        hashed_pw = generate_password_hash('admin123')
        admin = User(username='admin', password=hashed_pw, role='admin')
        db.session.add(admin)
        db.session.commit()
    Settings.get()

# ---------- ROUTES ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Username atau password salah')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    now = datetime.now()
    bulan = request.args.get('bulan', now.month, type=int)
    tahun = request.args.get('tahun', now.year, type=int)

    last_day = calendar.monthrange(tahun, bulan)[1]
    tgl_mulai = datetime(tahun, bulan, 1).date()
    tgl_akhir = datetime(tahun, bulan, last_day).date()

    pendapatan_kotor = db.session.query(func.sum(Pengiriman.total_biaya)).filter(
        Pengiriman.status == 'sukses',
        Pengiriman.tgl_pickup >= tgl_mulai,
        Pengiriman.tgl_pickup <= tgl_akhir
    ).scalar() or 0

    total_pengiriman = Pengiriman.query.filter(
        Pengiriman.tgl_pickup >= tgl_mulai,
        Pengiriman.tgl_pickup <= tgl_akhir
    ).count()

    recent_shipments = Pengiriman.query.order_by(Pengiriman.created_at.desc()).limit(5).all()

    setoran_list = Pengiriman.query.filter_by(status='sukses', verified=False).order_by(Pengiriman.tgl_pickup.desc()).limit(10).all()
    total_setoran = sum(p.total_biaya for p in setoran_list) if setoran_list else 0

    free_ship_list = Pengiriman.query.filter_by(status='retur', retur_verified=False).order_by(Pengiriman.tgl_pickup.desc()).limit(10).all()
    total_free_ship = sum(p.total_biaya for p in free_ship_list) if free_ship_list else 0

    bulan_list = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
                  'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']

    return render_template('dashboard.html',
                           pendapatan_hari_ini=pendapatan_kotor,
                           total_pengiriman=total_pengiriman,
                           recent_shipments=recent_shipments,
                           bulan=bulan,
                           tahun=tahun,
                           bulan_list=bulan_list,
                           setoran_list=setoran_list,
                           total_setoran=total_setoran,
                           free_ship_list=free_ship_list,
                           total_free_ship=total_free_ship)

@app.route('/input', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'petugas', 'kurir'])
def input_barang():
    form = InputBarangForm()
    pengirim_list = Pelanggan.query.filter_by(tipe='pengirim').all()
    penerima_list = Pelanggan.query.filter_by(tipe='penerima').all()

    pengirim_choices = []
    for p in pengirim_list:
        label = p.perusahaan.strip() if p.perusahaan and p.perusahaan.strip() else p.nama
        pengirim_choices.append((p.id, label))
    form.pengirim_id.choices = [(0, '-- Pilih Pengirim --')] + pengirim_choices

    penerima_choices = []
    for p in penerima_list:
        label = p.perusahaan.strip() if p.perusahaan and p.perusahaan.strip() else p.nama
        penerima_choices.append((p.id, label))
    form.penerima_id.choices = [(0, '-- Pilih Penerima --')] + penerima_choices

    if form.validate_on_submit():
        if form.pengirim_nama.data and form.pengirim_nama.data.strip():
            pengirim = Pelanggan.query.filter_by(nama=form.pengirim_nama.data.strip(), tipe='pengirim').first()
            if not pengirim:
                pengirim = Pelanggan(tipe='pengirim')
            pengirim.nama = form.pengirim_nama.data.strip()
            pengirim.perusahaan = form.pengirim_perusahaan.data.strip() if form.pengirim_perusahaan.data else ''
            pengirim.alamat = form.pengirim_alamat.data.strip() if form.pengirim_alamat.data else ''
            pengirim.no_telp = form.pengirim_no_telp.data.strip() if form.pengirim_no_telp.data else ''
            pengirim.kode_kota = form.pengirim_kota.data.strip() if form.pengirim_kota.data else ''
            db.session.add(pengirim)
            db.session.flush()
            pengirim_id = pengirim.id
        else:
            pengirim_id = form.pengirim_id.data

        if form.penerima_nama.data and form.penerima_nama.data.strip():
            penerima = Pelanggan.query.filter_by(nama=form.penerima_nama.data.strip(), tipe='penerima').first()
            if not penerima:
                penerima = Pelanggan(tipe='penerima')
            penerima.nama = form.penerima_nama.data.strip()
            penerima.perusahaan = form.penerima_perusahaan.data.strip() if form.penerima_perusahaan.data else ''
            penerima.alamat = form.penerima_alamat.data.strip() if form.penerima_alamat.data else ''
            penerima.no_telp = form.penerima_no_telp.data.strip() if form.penerima_no_telp.data else ''
            penerima.kode_kota = form.penerima_kota.data.strip() if form.penerima_kota.data else ''
            db.session.add(penerima)
            db.session.flush()
            penerima_id = penerima.id
        else:
            penerima_id = form.penerima_id.data

        if not pengirim_id or pengirim_id == 0:
            flash('Pilih pengirim atau isi data pengirim manual')
            return render_template('input_barang.html', form=form)
        if not penerima_id or penerima_id == 0:
            flash('Pilih penerima atau isi data penerima manual')
            return render_template('input_barang.html', form=form)

        resi = form.nomor_resi.data.strip() if form.nomor_resi.data else generate_resi_number()
        if Pengiriman.query.filter_by(nomor_resi=resi).first():
            flash('Nomor resi sudah digunakan')
            return render_template('input_barang.html', form=form)

        barcode_path = generate_barcode(resi)
        total = hitung_total(
            form.berat_kg.data, form.tarif_per_kg.data,
            form.ppn.data, form.asuransi.data, form.biaya_packing.data
        )
        pengiriman = Pengiriman(
            nomor_resi=resi,
            barcode_image=barcode_path,
            kota_asal=form.kota_asal.data,
            kota_tujuan=form.kota_tujuan.data,
            tgl_pickup=form.tgl_pickup.data,
            petugas_pickup=form.petugas_pickup.data,
            pengirim_id=pengirim_id,
            penerima_id=penerima_id,
            jenis_service=form.jenis_service.data,
            jenis_barang=form.jenis_barang.data,
            jumlah_koli=form.jumlah_koli.data,
            berat_kg=form.berat_kg.data,
            tarif_per_kg=form.tarif_per_kg.data,
            ppn=form.ppn.data,
            asuransi=form.asuransi.data,
            biaya_packing=form.biaya_packing.data,
            total_biaya=total,
            metode_pembayaran=form.metode_pembayaran.data,
            keterangan=form.keterangan.data
        )
        db.session.add(pengiriman)
        db.session.commit()

        if not pengiriman.barcode_image:
            pengiriman.barcode_image = generate_barcode(pengiriman.nomor_resi)
            db.session.commit()

        flash('Data pengiriman berhasil disimpan')
        return redirect(url_for('input_barang'))

    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    query_recent = Pengiriman.query.order_by(Pengiriman.created_at.desc())
    if from_date:
        try:
            from_d = datetime.strptime(from_date, '%Y-%m-%d').date()
            query_recent = query_recent.filter(Pengiriman.tgl_pickup >= from_d)
        except ValueError:
            pass
    if to_date:
        try:
            to_d = datetime.strptime(to_date, '%Y-%m-%d').date()
            query_recent = query_recent.filter(Pengiriman.tgl_pickup <= to_d)
        except ValueError:
            pass
    recent_shipments = query_recent.limit(25).all()

    return render_template('input_barang.html',
                           form=form,
                           recent_shipments=recent_shipments,
                           from_date=from_date,
                           to_date=to_date)

@app.route('/data')
@login_required
@role_required(['admin'])
def data_barang():
    dari = request.args.get('dari')
    sampai = request.args.get('sampai')
    query = Pengiriman.query
    if dari:
        try:
            tanggal_dari = datetime.strptime(dari, '%Y-%m-%d').date()
            query = query.filter(Pengiriman.tgl_pickup >= tanggal_dari)
        except ValueError:
            pass
    if sampai:
        try:
            tanggal_sampai = datetime.strptime(sampai, '%Y-%m-%d').date()
            query = query.filter(Pengiriman.tgl_pickup <= tanggal_sampai)
        except ValueError:
            pass
    pengiriman_list = query.order_by(Pengiriman.tgl_pickup.desc(), Pengiriman.created_at.desc()).all()
    return render_template('data_barang.html', data=pengiriman_list)

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def edit_barang(id):
    pengiriman = Pengiriman.query.get_or_404(id)
    form = InputBarangForm(obj=pengiriman)
    pengirim_list = Pelanggan.query.filter_by(tipe='pengirim').all()
    penerima_list = Pelanggan.query.filter_by(tipe='penerima').all()

    pengirim_choices = []
    for p in pengirim_list:
        label = p.perusahaan.strip() if p.perusahaan and p.perusahaan.strip() else p.nama
        pengirim_choices.append((p.id, label))
    form.pengirim_id.choices = [(0, '-- Pilih Pengirim --')] + pengirim_choices

    penerima_choices = []
    for p in penerima_list:
        label = p.perusahaan.strip() if p.perusahaan and p.perusahaan.strip() else p.nama
        penerima_choices.append((p.id, label))
    form.penerima_id.choices = [(0, '-- Pilih Penerima --')] + penerima_choices

    if request.method == 'GET':
        form.pengirim_id.data = pengiriman.pengirim_id
        form.penerima_id.data = pengiriman.penerima_id
        form.nomor_resi.data = pengiriman.nomor_resi
        form.kota_asal.data = pengiriman.kota_asal
        form.kota_tujuan.data = pengiriman.kota_tujuan
        form.tgl_pickup.data = pengiriman.tgl_pickup
        form.petugas_pickup.data = pengiriman.petugas_pickup
        form.jenis_service.data = pengiriman.jenis_service
        form.jenis_barang.data = pengiriman.jenis_barang
        form.jumlah_koli.data = pengiriman.jumlah_koli
        form.berat_kg.data = pengiriman.berat_kg
        form.tarif_per_kg.data = pengiriman.tarif_per_kg
        form.ppn.data = pengiriman.ppn
        form.asuransi.data = pengiriman.asuransi
        form.biaya_packing.data = pengiriman.biaya_packing
        form.metode_pembayaran.data = pengiriman.metode_pembayaran
        form.keterangan.data = pengiriman.keterangan

    if form.validate_on_submit():
        resi_baru = form.nomor_resi.data.strip() if form.nomor_resi.data else pengiriman.nomor_resi
        if resi_baru != pengiriman.nomor_resi:
            pengiriman.barcode_image = generate_barcode(resi_baru)
        pengiriman.nomor_resi = resi_baru
        pengiriman.kota_asal = form.kota_asal.data
        pengiriman.kota_tujuan = form.kota_tujuan.data
        pengiriman.tgl_pickup = form.tgl_pickup.data
        pengiriman.petugas_pickup = form.petugas_pickup.data
        pengiriman.pengirim_id = form.pengirim_id.data
        pengiriman.penerima_id = form.penerima_id.data
        pengiriman.jenis_service = form.jenis_service.data
        pengiriman.jenis_barang = form.jenis_barang.data
        pengiriman.jumlah_koli = form.jumlah_koli.data
        pengiriman.berat_kg = form.berat_kg.data
        pengiriman.tarif_per_kg = form.tarif_per_kg.data
        pengiriman.ppn = form.ppn.data
        pengiriman.asuransi = form.asuransi.data
        pengiriman.biaya_packing = form.biaya_packing.data
        pengiriman.total_biaya = hitung_total(form.berat_kg.data, form.tarif_per_kg.data, form.ppn.data, form.asuransi.data, form.biaya_packing.data)
        pengiriman.metode_pembayaran = form.metode_pembayaran.data
        pengiriman.keterangan = form.keterangan.data
        db.session.commit()

        if not pengiriman.barcode_image:
            pengiriman.barcode_image = generate_barcode(pengiriman.nomor_resi)
            db.session.commit()

        flash('Data berhasil diperbarui')
        return redirect(url_for('data_barang'))
    return render_template('edit_barang.html', form=form, pengiriman=pengiriman)

@app.route('/hapus/<int:id>')
@login_required
@role_required(['admin'])
def hapus_barang(id):
    pengiriman = Pengiriman.query.get_or_404(id)
    db.session.delete(pengiriman)
    db.session.commit()
    flash('Data berhasil dihapus')
    return redirect(url_for('data_barang'))

@app.route('/export')
@login_required
@role_required(['admin'])
def export_data():
    tgl = request.args.get('tanggal')
    query = Pengiriman.query
    if tgl:
        tgl_date = datetime.strptime(tgl, '%Y-%m-%d').date()
        query = query.filter_by(tgl_pickup=tgl_date)
    filepath = export_to_excel(query.all())
    if not os.path.exists(filepath):
        flash('Gagal membuat file Excel. Periksa folder exports.')
        return redirect(url_for('data_barang'))
    return send_file(filepath, as_attachment=True)

@app.route('/import', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def import_data():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or file.filename == '':
            flash('Pilih file Excel')
            return redirect(request.url)
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        file.save(filepath)
        try:
            added = import_from_excel(filepath)
            pengiriman_tanpa_barcode = Pengiriman.query.filter(
                (Pengiriman.barcode_image == None) | (Pengiriman.barcode_image == '')
            ).all()
            created = 0
            for p in pengiriman_tanpa_barcode:
                try:
                    p.barcode_image = generate_barcode(p.nomor_resi)
                    created += 1
                except Exception as e:
                    print(f"Gagal buat barcode untuk {p.nomor_resi}: {e}")
            db.session.commit()
            flash(f'Berhasil mengimpor {added} data. {created} barcode dibuat.')
        except Exception as e:
            flash(f'Gagal mengimpor: {str(e)}')
        return redirect(url_for('data_barang'))
    return render_template('import.html')

# ---------- PELANGGAN ----------
@app.route('/pelanggan')
@login_required
@role_required(['admin'])
def pelanggan_list():
    pelanggan = Pelanggan.query.order_by(Pelanggan.tipe, Pelanggan.nama).all()
    return render_template('pelanggan_list.html', pelanggan=pelanggan)

@app.route('/pelanggan/input', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def input_pelanggan():
    form = PelangganForm()
    if form.validate_on_submit():
        p = Pelanggan(
            tipe=form.tipe.data, nama=form.nama.data,
            perusahaan=form.perusahaan.data, alamat=form.alamat.data,
            no_telp=form.no_telp.data, kode_kota=form.kode_kota.data
        )
        db.session.add(p)
        db.session.commit()
        flash('Pelanggan berhasil ditambahkan')
        return redirect(url_for('pelanggan_list'))
    return render_template('input_pelanggan.html', form=form)

@app.route('/pelanggan/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def edit_pelanggan(id):
    pelanggan = Pelanggan.query.get_or_404(id)
    form = PelangganForm(obj=pelanggan)
    if form.validate_on_submit():
        pelanggan.nama = form.nama.data
        pelanggan.tipe = form.tipe.data
        pelanggan.perusahaan = form.perusahaan.data
        pelanggan.alamat = form.alamat.data
        pelanggan.no_telp = form.no_telp.data
        pelanggan.kode_kota = form.kode_kota.data
        db.session.commit()
        flash('Data pelanggan berhasil diperbarui')
        return redirect(url_for('pelanggan_list'))
    return render_template('edit_pelanggan.html', form=form, pelanggan=pelanggan)

@app.route('/get_pelanggan/<int:id>')
@login_required
def get_pelanggan(id):
    pelanggan = Pelanggan.query.get_or_404(id)
    return jsonify({
        'nama': pelanggan.nama,
        'perusahaan': pelanggan.perusahaan or '',
        'alamat': pelanggan.alamat or '',
        'no_telp': pelanggan.no_telp or '',
        'kota': pelanggan.kode_kota or ''
    })

# ---------- LAPORAN ----------
@app.route('/laporan')
@login_required
@role_required(['admin', 'kurir'])
def laporan():
    tgl_mulai = request.args.get('tgl_mulai')
    tgl_akhir = request.args.get('tgl_akhir')
    perusahaan = request.args.get('perusahaan', '')
    search = request.args.get('search', '')

    query = Pengiriman.query
    if tgl_mulai:
        tgl_mulai_date = datetime.strptime(tgl_mulai, '%Y-%m-%d')
        query = query.filter(Pengiriman.tgl_pickup >= tgl_mulai_date)
    if tgl_akhir:
        tgl_akhir_date = datetime.strptime(tgl_akhir, '%Y-%m-%d')
        query = query.filter(Pengiriman.tgl_pickup <= tgl_akhir_date)

    if perusahaan:
        query = query.filter(
            or_(
                Pengiriman.pengirim.has(Pelanggan.perusahaan.ilike(f'%{perusahaan}%')),
                Pengiriman.penerima.has(Pelanggan.perusahaan.ilike(f'%{perusahaan}%'))
            )
        )

    if search:
        query = query.filter(
            or_(
                Pengiriman.pengirim.has(Pelanggan.nama.ilike(f'%{search}%')),
                Pengiriman.penerima.has(Pelanggan.nama.ilike(f'%{search}%')),
                Pengiriman.nomor_resi.ilike(f'%{search}%'),
                Pengiriman.pengirim.has(Pelanggan.perusahaan.ilike(f'%{search}%')),
                Pengiriman.penerima.has(Pelanggan.perusahaan.ilike(f'%{search}%'))
            )
        )

    data = query.order_by(Pengiriman.tgl_pickup.desc()).all()
    perusahaan_list = db.session.query(Pelanggan.perusahaan).filter(Pelanggan.perusahaan != '').distinct().all()
    perusahaan_list = [p[0] for p in perusahaan_list]

    uang_masuk = 0
    biaya_total = 0
    laba_rugi = 0
    biaya_list = []
    if current_user.role == 'admin':
        uang_masuk = db.session.query(func.sum(Pengiriman.total_biaya)).filter(
            Pengiriman.status == 'sukses',
            Pengiriman.verified == True
        )
        if tgl_mulai:
            uang_masuk = uang_masuk.filter(Pengiriman.tgl_pickup >= tgl_mulai_date)
        if tgl_akhir:
            uang_masuk = uang_masuk.filter(Pengiriman.tgl_pickup <= tgl_akhir_date)
        uang_masuk = uang_masuk.scalar() or 0

        query_biaya = BiayaOperasional.query
        if tgl_mulai:
            query_biaya = query_biaya.filter(BiayaOperasional.tanggal >= tgl_mulai_date)
        if tgl_akhir:
            query_biaya = query_biaya.filter(BiayaOperasional.tanggal <= tgl_akhir_date)
        biaya_list = query_biaya.order_by(BiayaOperasional.tanggal.desc()).all()
        biaya_total = sum(b.jumlah for b in biaya_list) if biaya_list else 0
        laba_rugi = uang_masuk - biaya_total

    return render_template('laporan.html',
                           data=data,
                           perusahaan_list=perusahaan_list,
                           uang_masuk=uang_masuk,
                           biaya_total=biaya_total,
                           laba_rugi=laba_rugi,
                           biaya_list=biaya_list)

# ---------- TRANSAKSI PELANGGAN ----------
@app.route('/export_keuangan')
@login_required
@role_required(['admin'])
def export_keuangan():
    """
    Export laporan keuangan (uang masuk, biaya operasional, laba/rugi)
    ke file Excel dengan tiga sheet: Ringkasan, Biaya Operasional, Pemasukan.
    Parameter query: tgl_mulai, tgl_akhir (format YYYY-MM-DD).
    """
    tgl_mulai = request.args.get('tgl_mulai')
    tgl_akhir = request.args.get('tgl_akhir')

    # Konversi string tanggal ke objek datetime (jika ada)
    tgl_mulai_date = None
    tgl_akhir_date = None
    if tgl_mulai:
        try:
            tgl_mulai_date = datetime.strptime(tgl_mulai, '%Y-%m-%d')
        except ValueError:
            flash('Format tanggal mulai tidak valid')
            return redirect(url_for('laporan'))
    if tgl_akhir:
        try:
            tgl_akhir_date = datetime.strptime(tgl_akhir, '%Y-%m-%d')
        except ValueError:
            flash('Format tanggal akhir tidak valid')
            return redirect(url_for('laporan'))

    # 1. Ambil data uang masuk: pengiriman sukses dan sudah diverifikasi
    query_masuk = Pengiriman.query.filter(
        Pengiriman.status == 'sukses',
        Pengiriman.verified == True
    )
    if tgl_mulai_date:
        query_masuk = query_masuk.filter(Pengiriman.tgl_pickup >= tgl_mulai_date)
    if tgl_akhir_date:
        query_masuk = query_masuk.filter(Pengiriman.tgl_pickup <= tgl_akhir_date)

    pemasukan_list = query_masuk.order_by(Pengiriman.tgl_pickup.desc()).all()
    uang_masuk = sum(p.total_biaya for p in pemasukan_list) if pemasukan_list else 0

    # 2. Ambil data biaya operasional
    query_biaya = BiayaOperasional.query
    if tgl_mulai_date:
        query_biaya = query_biaya.filter(BiayaOperasional.tanggal >= tgl_mulai_date)
    if tgl_akhir_date:
        query_biaya = query_biaya.filter(BiayaOperasional.tanggal <= tgl_akhir_date)

    biaya_list = query_biaya.order_by(BiayaOperasional.tanggal.desc()).all()
    biaya_total = sum(b.jumlah for b in biaya_list) if biaya_list else 0

    # 3. Hitung laba/rugi
    laba_rugi = uang_masuk - biaya_total

    # 4. Siapkan DataFrame untuk setiap sheet Excel
    # Sheet Ringkasan
    summary_data = [
        {'Keterangan': 'Uang Masuk (Sukses & Diverifikasi)', 'Jumlah': uang_masuk},
        {'Keterangan': 'Total Biaya Operasional', 'Jumlah': biaya_total},
        {'Keterangan': 'Laba / Rugi', 'Jumlah': laba_rugi},
    ]
    df_summary = pd.DataFrame(summary_data)

    # Sheet Biaya Operasional
    biaya_data = []
    for b in biaya_list:
        biaya_data.append({
            'Tanggal': b.tanggal.strftime('%d/%m/%Y') if b.tanggal else '',
            'Jenis': b.jenis or '',
            'Keterangan': b.keterangan or '',
            'Jumlah': b.jumlah if b.jumlah else 0
        })
    df_biaya = pd.DataFrame(biaya_data, columns=['Tanggal', 'Jenis', 'Keterangan', 'Jumlah'])

    # Sheet Pemasukan (detail pengiriman sukses yang sudah diverifikasi)
    pemasukan_data = []
    for p in pemasukan_list:
        pemasukan_data.append({
            'No Resi': p.nomor_resi,
            'Tanggal Pickup': p.tgl_pickup.strftime('%d/%m/%Y') if p.tgl_pickup else '',
            'Pengirim': p.pengirim.nama if p.pengirim else '',
            'Penerima': p.penerima.nama if p.penerima else '',
            'Total Biaya': p.total_biaya
        })
    df_pemasukan = pd.DataFrame(pemasukan_data, columns=['No Resi', 'Tanggal Pickup', 'Pengirim', 'Penerima', 'Total Biaya'])

    # 5. Buat file Excel di memori (tanpa menyimpan ke disk)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_summary.to_excel(writer, sheet_name='Ringkasan', index=False)
        df_biaya.to_excel(writer, sheet_name='Biaya Operasional', index=False)
        df_pemasukan.to_excel(writer, sheet_name='Pemasukan', index=False)
    output.seek(0)

    # 6. Kirim file Excel sebagai attachment
    return send_file(
        output,
        as_attachment=True,
        download_name='laporan_keuangan.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

# ---------- SETTINGS ----------
@app.route('/settings', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def settings():
    settings_obj = Settings.get()
    form = SettingsForm(obj=settings_obj)
    if form.validate_on_submit():
        settings_obj.print_method = form.print_method.data
        settings_obj.resi_prefix = form.resi_prefix.data
        settings_obj.resi_date_format = form.resi_date_format.data
        settings_obj.resi_counter_length = form.resi_counter_length.data
        settings_obj.company_address = form.company_address.data
        settings_obj.company_phone = form.company_phone.data
        db.session.commit()
        flash('Pengaturan berhasil disimpan')
        return redirect(url_for('settings'))
    return render_template('settings.html', form=form)

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        user = User.query.get(current_user.id)
        if not check_password_hash(user.password, form.old_password.data):
            flash('Password lama salah')
        elif form.new_password.data != form.confirm_password.data:
            flash('Password baru tidak cocok')
        else:
            user.password = generate_password_hash(form.new_password.data)
            db.session.commit()
            flash('Password berhasil diubah')
            return redirect(url_for('dashboard'))
    return render_template('change_password.html', form=form)

# ---------- CETAK RESI ----------
@app.route('/cetak_resi', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def cetak_resi():
    settings = Settings.get()
    if request.method == 'POST':
        resi_ids = request.form.getlist('resi_ids')
        if not resi_ids:
            flash('Pilih minimal satu resi')
            return redirect(url_for('cetak_resi'))
        pengiriman_list = Pengiriman.query.filter(Pengiriman.id.in_(resi_ids)).all()

        if settings.print_method == 'pdf':
            try:
                import pdfkit
                html = render_template('resi_template.html', daftar=pengiriman_list)
                options = {
                    'enable-local-file-access': '',
                    'page-width': '215mm',
                    'page-height': '110mm',
                    'margin-top': '0',
                    'margin-bottom': '0',
                    'margin-left': '0',
                    'margin-right': '0'
                }
                config = pdfkit.configuration(wkhtmltopdf=r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe')
                pdf = pdfkit.from_string(html, False, options=options, configuration=config)
                response = make_response(pdf)
                response.headers['Content-Type'] = 'application/pdf'
                response.headers['Content-Disposition'] = 'inline; filename=resi.pdf'
                return response
            except Exception as e:
                flash(f'Gagal PDF: {e}. Menggunakan browser.')
        return render_template('resi_print.html', daftar=pengiriman_list)

    tgl = request.args.get('tanggal')
    pelanggan_id = request.args.get('pelanggan_id')
    query = Pengiriman.query
    if tgl:
        tgl_date = datetime.strptime(tgl, '%Y-%m-%d').date()
        query = query.filter_by(tgl_pickup=tgl_date)
    if pelanggan_id:
        pid = int(pelanggan_id)
        query = query.filter((Pengiriman.pengirim_id == pid) | (Pengiriman.penerima_id == pid))
    pengiriman = query.order_by(Pengiriman.tgl_pickup.desc()).all()
    pelanggan_list = Pelanggan.query.all()
    return render_template('cetak_resi.html', pengiriman=pengiriman, pelanggan_list=pelanggan_list)

# ---------- INVOICE ----------
@app.route('/invoice')
@login_required
@role_required(['admin'])
def invoice():
    semua_pelanggan = Pelanggan.query.order_by(Pelanggan.nama).all()
    now = datetime.now()
    return render_template('invoice.html',
                           semua_pelanggan=semua_pelanggan,
                           current_month=now.month,
                           current_year=now.year)

@app.route('/cetak_invoice')
@login_required
@role_required(['admin'])
def cetak_invoice():
    pelanggan_id = request.args.get('pelanggan_id', type=int)
    bulan = request.args.get('bulan', type=int)
    tahun = request.args.get('tahun', type=int)
    if not pelanggan_id or not bulan or not tahun:
        flash('Pilih pelanggan, bulan, dan tahun')
        return redirect(url_for('invoice'))

    pelanggan = Pelanggan.query.get_or_404(pelanggan_id)
    pengiriman = Pengiriman.query.filter(
        (Pengiriman.pengirim_id == pelanggan.id) | (Pengiriman.penerima_id == pelanggan.id),
        extract('month', Pengiriman.tgl_pickup) == bulan,
        extract('year', Pengiriman.tgl_pickup) == tahun
    ).order_by(Pengiriman.tgl_pickup).all()

    total = sum(p.total_biaya for p in pengiriman)
    now = datetime.now()

    bulan_id = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
                'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']
    last_day = calendar.monthrange(tahun, bulan)[1]
    start_date = f"1 {bulan_id[bulan-1]} {tahun}"
    end_date = f"{last_day} {bulan_id[bulan-1]} {tahun}"
    periode = f"{start_date} s.d {end_date}"

    settings = Settings.get()
    if settings.print_method == 'pdf':
        try:
            import pdfkit
            html = render_template('invoice_template.html',
                                   pelanggan=pelanggan,
                                   pengiriman=pengiriman,
                                   total=total,
                                   periode=periode,
                                   now=now,
                                   bulan=bulan,
                                   tahun=tahun)
            options = {
                'enable-local-file-access': '',
                'page-width': '215mm',
                'page-height': '330mm',
                'margin-top': '0',
                'margin-bottom': '0',
                'margin-left': '0',
                'margin-right': '0'
            }
            config = pdfkit.configuration(wkhtmltopdf=r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe')
            pdf = pdfkit.from_string(html, False, options=options, configuration=config)
            response = make_response(pdf)
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = 'inline; filename=invoice.pdf'
            return response
        except Exception as e:
            flash(f'Gagal PDF: {e}. Menggunakan browser.')
    return render_template('invoice_print.html',
                           pelanggan=pelanggan,
                           pengiriman=pengiriman,
                           total=total,
                           periode=periode,
                           now=now,
                           bulan=bulan,
                           tahun=tahun)

# ---------- UPDATE STATUS ----------
@app.route('/update_status/<int:id>', methods=['POST'])
@login_required
@role_required(['admin', 'kurir', 'petugas'])
def update_status(id):
    pengiriman = Pengiriman.query.get_or_404(id)
    new_status = request.form.get('status')
    if current_user.role == 'petugas' and new_status != 'sukses':
        flash('Anda hanya bisa mengupdate status menjadi Sukses.')
        return redirect(url_for('laporan'))
    if new_status in ['pending', 'sukses', 'hold', 'retur']:
        pengiriman.status = new_status
        db.session.commit()
        flash(f'Status resi {pengiriman.nomor_resi} diubah menjadi {new_status}')
    return redirect(url_for('laporan'))

@app.route('/update_status_multiple', methods=['POST'])
@login_required
@role_required(['admin', 'kurir', 'petugas'])
def update_status_multiple():
    ids = request.form.getlist('selected_ids')
    status_baru = request.form.get('status_baru')
    if current_user.role == 'petugas' and status_baru != 'sukses':
        flash('Anda hanya bisa mengupdate status menjadi Sukses.')
        return redirect(url_for('laporan'))
    if not ids:
        flash('Tidak ada pengiriman yang dipilih.')
        return redirect(url_for('laporan'))
    updated = 0
    for id_str in ids:
        p = Pengiriman.query.get(int(id_str))
        if p and p.status != status_baru:
            p.status = status_baru
            updated += 1
    db.session.commit()
    flash(f'{updated} pengiriman berhasil diupdate menjadi {status_baru}')
    return redirect(url_for('laporan'))

# ---------- VERIFIKASI ----------
@app.route('/verifikasi_ongkir/<int:id>')
@login_required
@role_required(['admin'])
def verifikasi_ongkir(id):
    pengiriman = Pengiriman.query.get_or_404(id)
    pengiriman.verified = True
    db.session.commit()
    flash(f'Setoran resi {pengiriman.nomor_resi} sudah diverifikasi.')
    return redirect(url_for('setoran_ongkir'))

@app.route('/verifikasi_retur/<int:id>')
@login_required
@role_required(['admin'])
def verifikasi_retur(id):
    pengiriman = Pengiriman.query.get_or_404(id)
    pengiriman.retur_verified = True
    db.session.commit()
    flash(f'Retur resi {pengiriman.nomor_resi} sudah diverifikasi.')
    return redirect(url_for('setoran_ongkir', tab='retur'))

@app.route('/verifikasi_ongkir_multiple', methods=['POST'])
@login_required
@role_required(['admin'])
def verifikasi_ongkir_multiple():
    ids = request.form.getlist('selected_ids')
    for id_str in ids:
        p = Pengiriman.query.get(int(id_str))
        if p:
            p.verified = True
    db.session.commit()
    flash(f'{len(ids)} setoran berhasil diverifikasi.')
    return redirect(url_for('setoran_ongkir'))

@app.route('/verifikasi_retur_multiple', methods=['POST'])
@login_required
@role_required(['admin'])
def verifikasi_retur_multiple():
    ids = request.form.getlist('selected_ids')
    for id_str in ids:
        p = Pengiriman.query.get(int(id_str))
        if p:
            p.retur_verified = True
    db.session.commit()
    flash(f'{len(ids)} retur berhasil diverifikasi.')
    return redirect(url_for('setoran_ongkir'))

# ---------- BIAYA OPERASIONAL ----------
@app.route('/biaya_operasional', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def biaya_operasional():
    form = BiayaOperasionalForm()
    if form.validate_on_submit():
        biaya = BiayaOperasional(
            tanggal=form.tanggal.data,
            jenis=form.jenis.data,
            keterangan=form.keterangan.data,
            jumlah=form.jumlah.data
        )
        db.session.add(biaya)
        db.session.commit()
        flash('Biaya operasional berhasil ditambahkan')
        return redirect(url_for('biaya_operasional'))
    biaya_list = BiayaOperasional.query.order_by(BiayaOperasional.tanggal.desc()).limit(30).all()
    return render_template('biaya_operasional.html', form=form, biaya_list=biaya_list)

@app.route('/biaya_operasional/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def edit_biaya(id):
    biaya = BiayaOperasional.query.get_or_404(id)
    form = BiayaOperasionalForm(obj=biaya)
    if form.validate_on_submit():
        biaya.tanggal = form.tanggal.data
        biaya.jenis = form.jenis.data
        biaya.keterangan = form.keterangan.data
        biaya.jumlah = form.jumlah.data
        db.session.commit()
        flash('Biaya operasional berhasil diperbarui')
        return redirect(url_for('biaya_operasional'))
    return render_template('edit_biaya.html', form=form, biaya=biaya)

@app.route('/biaya_operasional/hapus/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def hapus_biaya(id):
    biaya = BiayaOperasional.query.get_or_404(id)
    db.session.delete(biaya)
    db.session.commit()
    flash('Biaya operasional berhasil dihapus')
    return redirect(url_for('biaya_operasional'))

@app.route('/import_biaya', methods=['POST'])
@login_required
@role_required(['admin'])
def import_biaya():
    file = request.files.get('file')
    if not file or file.filename == '':
        flash('Pilih file Excel')
        return redirect(url_for('biaya_operasional'))
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    file.save(filepath)
    try:
        added = import_biaya_from_excel(filepath)
        flash(f'Berhasil mengimpor {added} biaya operasional')
    except Exception as e:
        flash(f'Gagal mengimpor: {str(e)}')
    return redirect(url_for('biaya_operasional'))

# ---------- SETORAN ONGKIR ----------
@app.route('/setoran_ongkir')
@login_required
@role_required(['admin'])
def setoran_ongkir():
    tgl_mulai = request.args.get('tgl_mulai')
    tgl_akhir = request.args.get('tgl_akhir')
    bulan = request.args.get('bulan')
    tahun = request.args.get('tahun')
    pelanggan_id = request.args.get('pelanggan_id')
    no_resi = request.args.get('no_resi')
    tab = request.args.get('tab', 'sukses')

    query_sukses = Pengiriman.query.filter_by(status='sukses', verified=False)
    query_retur = Pengiriman.query.filter_by(status='retur', retur_verified=False)

    if tgl_mulai:
        tgl_mulai_date = datetime.strptime(tgl_mulai, '%Y-%m-%d')
        query_sukses = query_sukses.filter(Pengiriman.tgl_pickup >= tgl_mulai_date)
        query_retur = query_retur.filter(Pengiriman.tgl_pickup >= tgl_mulai_date)
    if tgl_akhir:
        tgl_akhir_date = datetime.strptime(tgl_akhir, '%Y-%m-%d')
        query_sukses = query_sukses.filter(Pengiriman.tgl_pickup <= tgl_akhir_date)
        query_retur = query_retur.filter(Pengiriman.tgl_pickup <= tgl_akhir_date)
    if bulan and tahun:
        bulan = int(bulan)
        tahun = int(tahun)
        query_sukses = query_sukses.filter(
            extract('month', Pengiriman.tgl_pickup) == bulan,
            extract('year', Pengiriman.tgl_pickup) == tahun
        )
        query_retur = query_retur.filter(
            extract('month', Pengiriman.tgl_pickup) == bulan,
            extract('year', Pengiriman.tgl_pickup) == tahun
        )
    if pelanggan_id:
        pid = int(pelanggan_id)
        query_sukses = query_sukses.filter(
            (Pengiriman.pengirim_id == pid) | (Pengiriman.penerima_id == pid)
        )
        query_retur = query_retur.filter(
            (Pengiriman.pengirim_id == pid) | (Pengiriman.penerima_id == pid)
        )
    if no_resi:
        query_sukses = query_sukses.filter(Pengiriman.nomor_resi.like(f'%{no_resi}%'))
        query_retur = query_retur.filter(Pengiriman.nomor_resi.like(f'%{no_resi}%'))

    data_sukses = query_sukses.order_by(Pengiriman.tgl_pickup.desc()).all()
    data_retur = query_retur.order_by(Pengiriman.tgl_pickup.desc()).all()

    total_ongkir_sukses = sum(p.total_biaya for p in data_sukses)
    total_ongkir_retur = sum(p.total_biaya for p in data_retur)

    pelanggan_list = Pelanggan.query.order_by(Pelanggan.nama).all()

    return render_template('setoran_ongkir.html',
                           data_sukses=data_sukses,
                           data_retur=data_retur,
                           total_ongkir_sukses=total_ongkir_sukses,
                           total_ongkir_retur=total_ongkir_retur,
                           pelanggan_list=pelanggan_list,
                           tab=tab)

# ---------- DAILY DELIVERY ----------
@app.route('/daily_delivery')
@login_required
@role_required(['admin', 'kurir'])
def daily_delivery():
    tanggal = request.args.get('tanggal')
    if not tanggal:
        tanggal = datetime.now().strftime('%Y-%m-%d')
    try:
        tgl = datetime.strptime(tanggal, '%Y-%m-%d').date()
    except ValueError:
        tgl = datetime.now().date()

    pengiriman_hari_ini = Pengiriman.query.filter_by(tgl_pickup=tgl).order_by(Pengiriman.nomor_resi).all()

    total_cash = sum(p.total_biaya for p in pengiriman_hari_ini if p.metode_pembayaran == 'cash')
    total_credit = sum(p.total_biaya for p in pengiriman_hari_ini if p.metode_pembayaran == 'credit')
    total_free_ship = sum(p.total_biaya for p in pengiriman_hari_ini if p.status == 'retur')

    return render_template('daily_delivery.html',
                           tanggal=tgl,
                           pengiriman_hari_ini=pengiriman_hari_ini,
                           total_cash=total_cash,
                           total_credit=total_credit,
                           total_free_ship=total_free_ship)

# ---------- MANAJEMEN USER ----------
@app.route('/users')
@login_required
@role_required(['admin'])
def user_list():
    users = User.query.all()
    return render_template('user_list.html', users=users)

@app.route('/users/add', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def add_user():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')

        if User.query.filter_by(username=username).first():
            flash('Username sudah digunakan')
            return redirect(url_for('add_user'))

        hashed_pw = generate_password_hash(password)
        new_user = User(username=username, password=hashed_pw, role=role)
        db.session.add(new_user)
        db.session.commit()
        flash('User berhasil ditambahkan')
        return redirect(url_for('user_list'))

    return render_template('add_user.html')

@app.route('/users/delete/<int:id>')
@login_required
@role_required(['admin'])
def delete_user(id):
    user = User.query.get_or_404(id)
    if user.username == 'admin':
        flash('Admin utama tidak dapat dihapus')
        return redirect(url_for('user_list'))
    db.session.delete(user)
    db.session.commit()
    flash('User berhasil dihapus')
    return redirect(url_for('user_list'))

if __name__ == '__main__':
    app.run(debug=True)