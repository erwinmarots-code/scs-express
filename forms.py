from flask_wtf import FlaskForm
from wtforms import StringField, DateField, SelectField, FloatField, IntegerField, TextAreaField, PasswordField
from wtforms.validators import DataRequired, Optional

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])

class InputBarangForm(FlaskForm):
    nomor_resi = StringField('Nomor Resi', validators=[Optional()])
    kota_asal = StringField('Kota Asal', validators=[DataRequired()])
    kota_tujuan = StringField('Kota Tujuan', validators=[DataRequired()])
    tgl_pickup = DateField('Tanggal Pickup', format='%Y-%m-%d', validators=[DataRequired()])
    petugas_pickup = StringField('Petugas Pickup', validators=[DataRequired()])

    pengirim_id = SelectField('Pengirim (Pilih)', coerce=int, validators=[Optional()])
    penerima_id = SelectField('Penerima (Pilih)', coerce=int, validators=[Optional()])

    pengirim_nama = StringField('Nama Pengirim')
    pengirim_perusahaan = StringField('Perusahaan Pengirim')
    pengirim_alamat = StringField('Alamat Pengirim')
    pengirim_no_telp = StringField('No Telp Pengirim')
    pengirim_kota = StringField('Kota Pengirim')

    penerima_nama = StringField('Nama Penerima')
    penerima_perusahaan = StringField('Perusahaan Penerima')
    penerima_alamat = StringField('Alamat Penerima')
    penerima_no_telp = StringField('No Telp Penerima')
    penerima_kota = StringField('Kota Penerima')

    jenis_service = SelectField('Jenis Service', choices=[('regular','Regular'), ('express','Express')])
    jenis_barang = SelectField('Jenis Barang', choices=[('paket','Paket'), ('dokumen','Dokumen')])
    jumlah_koli = IntegerField('Jumlah Koli', validators=[DataRequired()])
    berat_kg = FloatField('Berat (kg)', validators=[DataRequired()])
    tarif_per_kg = FloatField('Tarif per kg', validators=[DataRequired()])
    ppn = FloatField('PPN', default=0.0)
    asuransi = FloatField('Disc (%)', default=0.0)
    biaya_packing = FloatField('Biaya Packing', default=0.0)
    metode_pembayaran = SelectField('Metode Pembayaran', choices=[('cash','Cash'), ('credit','Credit')])
    keterangan = TextAreaField('Keterangan')

class PelangganForm(FlaskForm):
    tipe = SelectField('Tipe', choices=[('pengirim','Pengirim'), ('penerima','Penerima')])
    nama = StringField('Nama', validators=[DataRequired()])
    perusahaan = StringField('Perusahaan')
    alamat = TextAreaField('Alamat')
    no_telp = StringField('No. Telepon')
    kode_kota = StringField('Kode Kota')

class SettingsForm(FlaskForm):
    print_method = SelectField('Metode Cetak Resi', choices=[
        ('browser', 'Cetak via Browser (HTML)'),
        ('pdf', 'Cetak PDF (memerlukan wkhtmltopdf)')
    ])
    resi_prefix = StringField('Prefix Resi (opsional)')
    resi_date_format = SelectField('Format Tanggal dalam Resi', choices=[
        ('%Y%m%d', 'YYYYMMDD'),
        ('%d%m%Y', 'DDMMYYYY'),
        ('%y%m%d', 'YYMMDD'),
    ])
    resi_counter_length = IntegerField('Panjang Nomor Urut', default=4)
    company_address = StringField('Alamat Perusahaan')
    company_phone = StringField('No. Telepon Perusahaan')

class ChangePasswordForm(FlaskForm):
    old_password = PasswordField('Password Lama', validators=[DataRequired()])
    new_password = PasswordField('Password Baru', validators=[DataRequired()])
    confirm_password = PasswordField('Konfirmasi Password Baru', validators=[DataRequired()])

class StatusForm(FlaskForm):
    status = SelectField('Status', choices=[
        ('pending', 'Manifested'),
        ('sukses', 'Sukses'),
        ('hold', 'TOP'),
        ('retur', 'Free Ship.')
    ])

class BiayaOperasionalForm(FlaskForm):
    tanggal = DateField('Tanggal', format='%Y-%m-%d', validators=[DataRequired()])
    jenis = SelectField('Jenis', choices=[('', '-- Pilih --'), ('UPG', 'UPG'), ('PLP', 'PLP'), ('PRE', 'PRE'), ('ASKARINDO', 'ASKARINDO')])
    keterangan = StringField('Keterangan')
    jumlah = FloatField('Jumlah (Rp)', validators=[DataRequired()])