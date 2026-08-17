import json
import os

LOCALES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")

# ---- per-locale translations (keys not listed fall back to English) ----
CHANGE_DUE = {
    "en": "Change Due", "de": "Rückgeld", "es": "Cambio a devolver",
    "fr": "Monnaie à rendre", "pt": "Troco a devolver", "ar": "المبلغ المستحق إرجاعه",
}
SELECT_A_PATIENT = {
    "en": "Select a patient", "de": "Patient auswählen", "es": "Seleccionar paciente",
    "fr": "Sélectionner un patient", "pt": "Selecionar paciente", "ar": "اختر مريضاً",
}
PATIENT_LABEL = {
    "en": "Patient", "de": "Patient", "es": "Paciente", "fr": "Patient",
    "pt": "Paciente", "ar": "المريض",
}
SIGNED_IN_AS = {
    "en": "Signed in as %s (%s)", "de": "Angemeldet als %s (%s)", "es": "Sesión iniciada como %s (%s)",
    "fr": "Connecté en tant que %s (%s)", "pt": "Conectado como %s (%s)", "ar": "تم تسجيل الدخول باسم %s (%s)",
}
PERMISSION_REQUIRED = {
    "en": "Requires the '%s' permission", "de": "Benötigt die Berechtigung '%s'",
    "es": "Requiere el permiso '%s'", "fr": "Nécessite la permission '%s'",
    "pt": "Requer a permissão '%s'", "ar": "يتطلب إذن '%s'",
}
REGION_FIELDS = {
    "en": "Region-specific patient identifiers (change with your region settings)",
    "de": "Regionsspezifische Patientenkennungen (über Ihre Regionseinstellungen änderbar)",
    "es": "Identificadores de paciente específicos de la región (cámbielos en la configuración regional)",
    "fr": "Identifiants patients propres à la région (modifiables dans les paramètres régionaux)",
    "pt": "Identificadores de paciente específicos da região (altere nas configurações regionais)",
    "ar": "معرفات المريض الخاصة بالمنطقة (تتغير عبر إعدادات المنطقة)",
}
# region field labels
FIELD = {
    "field_dea_number": {
        "en": "DEA Number", "de": "DEA-Nummer", "es": "Número DEA", "fr": "Numéro DEA",
        "pt": "Número DEA", "ar": "رقم DEA"},
    "field_npi": {
        "en": "NPI", "de": "NPI", "es": "NPI", "fr": "NPI", "pt": "NPI", "ar": "NPI"},
    "field_nhs_number": {
        "en": "NHS Number", "de": "NHS-Nummer", "es": "Número NHS", "fr": "Numéro NHS",
        "pt": "Número NHS", "ar": "رقم NHS"},
    "field_gphc_number": {
        "en": "GPhC Number", "de": "GPhC-Nummer", "es": "Número GPhC", "fr": "Numéro GPhC",
        "pt": "Número GPhC", "ar": "رقم GPhC"},
    "field_exemption_category": {
        "en": "Exemption Category", "de": "Befreiungskategorie", "es": "Categoría de exención",
        "fr": "Catégorie d'exemption", "pt": "Categoria de isenção", "ar": "فئة الإعفاء"},
    "field_pzn_code": {
        "en": "PZN", "de": "PZN", "es": "PZN", "fr": "PZN", "pt": "PZN", "ar": "PZN"},
    "field_insurance_bin": {
        "en": "Insurance BIN", "de": "Versicherungs-BIN", "es": "BIN de seguro", "fr": "BIN d'assurance",
        "pt": "BIN do seguro", "ar": "BIN التأمين"},
    "field_insurance_pcn": {
        "en": "Insurance PCN", "de": "Versicherungs-PCN", "es": "PCN de seguro", "fr": "PCN d'assurance",
        "pt": "PCN do seguro", "ar": "PCN التأمين"},
    "field_scheme_pcn": {
        "en": "Scheme PCN", "de": "Schema-PCN", "es": "PCN del esquema", "fr": "PCN du régime",
        "pt": "PCN do esquema", "ar": "PCN الخطة"},
    "field_group_number": {
        "en": "Group Number", "de": "Gruppennummer", "es": "Número de grupo", "fr": "Numéro de groupe",
        "pt": "Número de grupo", "ar": "رقم المجموعة"},
}
# tooltip keys
TIP = {
    "tip_nav_settings": {
        "en": "Application settings, language, and theme", "de": "Anwendungseinstellungen, Sprache und Design",
        "es": "Configuración, idioma y tema", "fr": "Paramètres, langue et thème",
        "pt": "Configurações, idioma e tema", "ar": "إعدادات التطبيق واللغة والسمة"},
    "tip_nav_enterprise_settings": {
        "en": "Enterprise configuration (admin only)", "de": "Unternehmenskonfiguration (nur Admin)",
        "es": "Configuración empresarial (solo admin)", "fr": "Configuration d'entreprise (admin)",
        "pt": "Configuração empresarial (somente admin)", "ar": "إعدادات المؤسسة (المسؤول فقط)"},
    "tip_nav_status_dashboard": {
        "en": "Operational metrics and reports", "de": "Betriebskennzahlen und Berichte",
        "es": "Métricas e informes", "fr": "Indicateurs et rapports", "pt": "Métricas e relatórios",
        "ar": "المقاييس والتقارير التشغيلية"},
    "tip_backup_database": {
        "en": "Create a timestamped backup of the pharmacy database", "de": "Sicherung der Apotheken-Datenbank erstellen",
        "es": "Crear una copia de seguridad de la base de datos", "fr": "Créer une sauvegarde de la base de données",
        "pt": "Criar um backup da base de dados", "ar": "إنشاء نسخة احتياطية من قاعدة البيانات"},
    "tip_audit_log": {
        "en": "View the security and compliance audit trail", "de": "Prüfprotokoll anzeigen",
        "es": "Ver el registro de auditoría", "fr": "Afficher le journal d'audit",
        "pt": "Ver o registro de auditoria", "ar": "عرض سجل المراجعة"},
    "tip_save_settings": {
        "en": "Save changes to configuration", "de": "Änderungen speichern", "es": "Guardar cambios",
        "fr": "Enregistrer les modifications", "pt": "Salvar alterações", "ar": "حفظ التغييرات"},
    "tip_pos_payment_method": {
        "en": "Choose how the customer pays", "de": "Zahlungsart wählen", "es": "Elija el método de pago",
        "fr": "Choisissez le moyen de paiement", "pt": "Escolha a forma de pagamento", "ar": "اختر طريقة الدفع"},
    "tip_pos_amount_tendered": {
        "en": "Cash amount received from the customer", "de": "Erhaltener Bargeldbetrag",
        "es": "Efectivo recibido del cliente", "fr": "Montant en espèces reçu", "pt": "Valor em dinheiro recebido",
        "ar": "المبلغ النقدي المستلم من العميل"},
    "tip_pos_tax_exempt": {
        "en": "Mark this sale as exempt from sales tax / VAT", "de": "Verkauf steuerfrei markieren",
        "es": "Marcar esta venta como exenta de impuestos", "fr": "Marquer exempt de taxe/TVA",
        "pt": "Marcar esta venda como isenta de impostos", "ar": "تحديد هذه المبيعات معفاة من الضريبة"},
    "tip_pos_process_payment": {
        "en": "Validate the cart and complete the sale", "de": "Verkauf abschließen", "es": "Completar la venta",
        "fr": "Finaliser la vente", "pt": "Concluir a venda", "ar": "إتمام عملية البيع"},
    "tip_region_fields": {
        "en": "Fields shown depend on your detected region", "de": "Felder hängen von Ihrer Region ab",
        "es": "Los campos dependen de su región", "fr": "Les champs dépendent de votre région",
        "pt": "Os campos dependem da sua região", "ar": "الحقول تظهر حسب منطقتك"},
    "tip_settings_admin_only": {
        "en": "Administrative controls are hidden without settings.manage", "de": "Admin-Bereich ohne settings.manage ausgeblendet",
        "es": "Controles de administración ocultos sin settings.manage", "fr": "Contrôles admin masqués sans settings.manage",
        "pt": "Controles administrativos ocultos sem settings.manage", "ar": "الأدوات الإدارية مخفية بدون settings.manage"},
}

DRIFT_KEYS = [
    "region_indicator", "change_region", "change_region_c", "current_region",
    "region_changed", "region_changes_may_affect", "region_banner_title",
    "region_banner_msg", "region_banner_dismiss", "region_banner_change",
]


def fix_value(val):
    if not isinstance(val, str):
        return val
    return val[:-1] if val.endswith(":") else val


for lang in ["en", "de", "es", "fr", "pt", "ar"]:
    path = os.path.join(LOCALES, f"{lang}.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f, strict=False)

    # T2a strip trailing colon from change + patient_label
    for k in ("change", "patient_label"):
        if k in data:
            data[k] = fix_value(data[k])

    # T2b translate placeholders
    data["change_due"] = CHANGE_DUE[lang]
    data["select_a_patient"] = SELECT_A_PATIENT[lang]
    data["patient_label"] = PATIENT_LABEL[lang]

    # T2c drift keys (only missing ones, keep existing)
    for k in DRIFT_KEYS:
        data.setdefault(k, "region_indicator" if k == "region_indicator" else k)

    # T2d new keys
    data["signed_in_as"] = SIGNED_IN_AS[lang]
    data["permission_required"] = PERMISSION_REQUIRED[lang]
    data["tip_region_fields"] = REGION_FIELDS[lang]
    for fk, tr in FIELD.items():
        data.setdefault(fk, tr[lang])
    for tk, tr in TIP.items():
        data.setdefault(tk, tr[lang])

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

print("locale fixes applied")
