"""Unit Tests fuer EmployeeService.

Testet:
- PII-Maskierung
- Input-Sanitization
- CRUD-Operationen
- Audit-Logging
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.personal.employee_service import EmployeeService, employee_service


class TestPIIMasking:
    """Tests fuer PII-Maskierung."""

    def test_mask_tax_id(self):
        """Tax ID sollte auf letzte 4 Zeichen maskiert werden."""
        service = EmployeeService()
        result = service._mask_pii_field('tax_id', '12345678901')
        assert result == '***8901'

    def test_mask_short_tax_id(self):
        """Kurze Tax ID sollte vollstaendig maskiert werden."""
        service = EmployeeService()
        result = service._mask_pii_field('tax_id', '123')
        assert result == '***'

    def test_mask_social_security_number(self):
        """SSN sollte maskiert werden."""
        service = EmployeeService()
        result = service._mask_pii_field('social_security_number', '123-45-6789')
        assert result == '***-***-****'

    def test_mask_iban(self):
        """IBAN sollte auf erste 4 + letzte 4 Zeichen maskiert werden."""
        service = EmployeeService()
        result = service._mask_pii_field('iban', 'DE89370400440532013000')
        assert result == 'DE89****3000'

    def test_mask_short_iban(self):
        """Kurze IBAN sollte maskiert werden."""
        service = EmployeeService()
        result = service._mask_pii_field('iban', 'DE89')
        assert result == '****'

    def test_mask_private_email(self):
        """Private Email sollte maskiert werden."""
        service = EmployeeService()
        result = service._mask_pii_field('private_email', 'max.mustermann@gmail.com')
        assert result == 'max***@***'

    def test_mask_email_at_sign(self):
        """Email ohne genug Zeichen vor @ sollte behandelt werden."""
        service = EmployeeService()
        result = service._mask_pii_field('private_email', 'm@x.com')
        assert '***' in result

    def test_mask_private_phone(self):
        """Private Telefonnummer sollte maskiert werden."""
        service = EmployeeService()
        result = service._mask_pii_field('private_phone', '+49 123 456 7890')
        assert result == '***7890'

    def test_mask_date_of_birth(self):
        """Geburtsdatum sollte komplett ausgeblendet werden."""
        service = EmployeeService()
        result = service._mask_pii_field('date_of_birth', date(1990, 5, 15))
        assert result is None

    def test_mask_health_insurance_number(self):
        """Krankenversicherungsnummer sollte maskiert werden."""
        service = EmployeeService()
        result = service._mask_pii_field('health_insurance_number', 'A123456789')
        assert result == '***6789'

    def test_mask_none_value(self):
        """None-Werte sollten None bleiben."""
        service = EmployeeService()
        result = service._mask_pii_field('tax_id', None)
        assert result is None

    def test_mask_empty_string(self):
        """Leere Strings sollten leer bleiben."""
        service = EmployeeService()
        result = service._mask_pii_field('tax_id', '')
        assert result == ''

    def test_non_pii_field_unchanged(self):
        """Nicht-PII-Felder sollten unveraendert bleiben."""
        service = EmployeeService()
        result = service._mask_pii_field('first_name', 'Max')
        assert result == 'Max'


class TestInputSanitization:
    """Tests fuer Input-Sanitization."""

    def test_sanitize_text_fields(self):
        """Text-Felder sollten sanitiert werden."""
        service = EmployeeService()
        data = {
            'first_name': '  Max  ',
            'last_name': 'Mustermann<script>',
            'notes': 'Notiz mit Inhalt',
        }
        result = service._sanitize_input(data)

        # Sollte getrimmt sein
        assert result['first_name'] != '  Max  '
        # Script-Tags sollten entfernt sein
        assert '<script>' not in result.get('last_name', '')

    def test_sanitize_preserves_valid_data(self):
        """Gueltge Daten sollten erhalten bleiben."""
        service = EmployeeService()
        data = {
            'first_name': 'Max',
            'last_name': 'Mustermann',
            'employee_number': '12345',
        }
        result = service._sanitize_input(data)
        assert result['first_name'] == 'Max'
        assert result['last_name'] == 'Mustermann'

    def test_sanitize_non_string_fields(self):
        """Nicht-String-Felder sollten unveraendert bleiben."""
        service = EmployeeService()
        data = {
            'is_active': True,
            'salary': Decimal('50000'),
        }
        result = service._sanitize_input(data)
        assert result['is_active'] is True
        assert result['salary'] == Decimal('50000')


class TestEmployeeToDictConversion:
    """Tests fuer _employee_to_dict Konvertierung."""

    @pytest.fixture
    def mock_employee(self):
        """Erstellt einen Mock-Employee."""
        employee = MagicMock()
        employee.id = uuid4()
        employee.first_name = 'Max'
        employee.last_name = 'Mustermann'
        employee.full_name = 'Max Mustermann'
        employee.employee_number = '12345'
        employee.email = 'max.mustermann@company.com'
        employee.tax_id = '12345678901'
        employee.social_security_number = '123-45-6789'
        employee.iban = 'DE89370400440532013000'
        employee.bic = 'COBADEFFXXX'
        employee.health_insurance_number = 'A123456789'
        employee.private_email = 'max@gmail.com'
        employee.private_phone = '+49123456789'
        employee.date_of_birth = date(1990, 5, 15)
        employee.place_of_birth = 'Berlin'
        employee.nationality = 'DE'
        employee.is_active = True
        employee.department_id = uuid4()
        employee.position_id = uuid4()
        employee.department = None
        employee.position = None
        employee.hire_date = date(2020, 1, 15)
        employee.termination_date = None
        employee.created_at = datetime.now(timezone.utc)
        employee.updated_at = None
        return employee

    def test_to_dict_with_pii_masked(self, mock_employee):
        """Dict mit maskierten PII-Feldern."""
        service = EmployeeService()
        result = service._employee_to_dict(mock_employee, mask_pii=True)

        # PII sollte maskiert sein
        assert result['tax_id'] == '***8901'
        assert result['social_security_number'] == '***-***-****'
        assert result['iban'] == 'DE89****3000'
        assert result['private_email'] == 'max***@***'
        assert result['date_of_birth'] is None
        assert result['pii_masked'] is True

    def test_to_dict_with_pii_visible(self, mock_employee):
        """Dict mit sichtbaren PII-Feldern."""
        service = EmployeeService()
        result = service._employee_to_dict(mock_employee, mask_pii=False)

        # PII sollte sichtbar sein
        assert result['tax_id'] == '12345678901'
        assert result['social_security_number'] == '123-45-6789'
        assert result['iban'] == 'DE89370400440532013000'
        assert result['date_of_birth'] == '1990-05-15'
        assert result['pii_masked'] is False

    def test_to_dict_basic_fields(self, mock_employee):
        """Basis-Felder sollten korrekt sein."""
        service = EmployeeService()
        result = service._employee_to_dict(mock_employee, mask_pii=True)

        assert result['first_name'] == 'Max'
        assert result['last_name'] == 'Mustermann'
        assert result['full_name'] == 'Max Mustermann'
        assert result['employee_number'] == '12345'
        assert result['is_active'] is True


class TestListEmployees:
    """Tests fuer list_employees."""

    @pytest.fixture
    def mock_db(self):
        """Erstellt eine Mock-DB-Session."""
        db = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_list_with_pagination(self, mock_db):
        """Liste mit Paginierung."""
        service = EmployeeService()
        company_id = uuid4()

        # Mock Ergebnis
        mock_employee = MagicMock()
        mock_employee.id = uuid4()
        mock_employee.first_name = 'Max'
        mock_employee.last_name = 'Mustermann'
        mock_employee.full_name = 'Max Mustermann'
        mock_employee.employee_number = '12345'
        mock_employee.email = 'max@company.com'
        mock_employee.is_active = True
        mock_employee.department_id = None
        mock_employee.position_id = None
        mock_employee.department = None
        mock_employee.position = None
        mock_employee.tax_id = None
        mock_employee.social_security_number = None
        mock_employee.iban = None
        mock_employee.bic = None
        mock_employee.health_insurance_number = None
        mock_employee.private_email = None
        mock_employee.private_phone = None
        mock_employee.date_of_birth = None
        mock_employee.place_of_birth = None
        mock_employee.nationality = None
        mock_employee.hire_date = date(2020, 1, 15)
        mock_employee.termination_date = None
        mock_employee.created_at = datetime.now(timezone.utc)
        mock_employee.updated_at = None

        # Mock Query-Ergebnis
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_employee]
        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=1)),  # Count
            mock_result,  # Actual query
        ]

        employees, total = await service.list_employees(
            db=mock_db,
            company_id=company_id,
            mask_pii=True,
            page=1,
            per_page=50,
        )

        assert total == 1
        assert len(employees) == 1
        assert employees[0]['first_name'] == 'Max'


class TestPIIFields:
    """Tests fuer PII_FIELDS Konfiguration."""

    def test_all_pii_fields_have_mask_function(self):
        """Alle PII-Felder sollten eine Maskierungsfunktion haben."""
        service = EmployeeService()
        for field in service.PII_FIELDS:
            assert field in service.PII_FIELDS
            # Jedes Feld sollte maskierbar sein
            assert callable(service.PII_FIELDS[field])

    def test_pii_field_count(self):
        """Erwartete Anzahl PII-Felder."""
        service = EmployeeService()
        # tax_id, ssn, iban, bic, health_insurance, private_email,
        # private_phone, dob, place_of_birth, nationality
        assert len(service.PII_FIELDS) >= 10
