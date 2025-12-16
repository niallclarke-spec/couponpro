"""
Tests for Clerk authentication module.
Mocks JWT verification - no real Clerk calls.
"""
import os
import pytest
from unittest.mock import patch, MagicMock


class TestVerifyClerkToken:
    """Tests for verify_clerk_token function."""
    
    def test_returns_none_when_jwks_url_not_configured(self):
        """Should return None when CLERK_JWKS_URL is not set."""
        with patch.dict(os.environ, {}, clear=True):
            if 'CLERK_JWKS_URL' in os.environ:
                del os.environ['CLERK_JWKS_URL']
            
            from auth.clerk_auth import verify_clerk_token, AuthFailureReason
            result, failure_reason = verify_clerk_token("fake.jwt.token")
            assert result is None
            assert failure_reason == AuthFailureReason.JWKS_NOT_CONFIGURED
    
    def test_returns_user_info_on_valid_token(self):
        """Should return user info when token is valid."""
        mock_claims = {
            'sub': 'user_123',
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'image_url': 'https://example.com/avatar.jpg',
            'exp': 9999999999,
            'iat': 1000000000
        }
        
        with patch.dict(os.environ, {'CLERK_JWKS_URL': 'https://example.com/.well-known/jwks.json'}):
            with patch('auth.clerk_auth._get_jwks_client') as mock_client:
                mock_key = MagicMock()
                mock_key.key = 'fake_key'
                mock_client.return_value.get_signing_key_from_jwt.return_value = mock_key
                
                with patch('jwt.decode', return_value=mock_claims):
                    from auth.clerk_auth import verify_clerk_token
                    result, failure_reason = verify_clerk_token("valid.jwt.token")
                    
                    assert result is not None
                    assert failure_reason is None
                    assert result['clerk_user_id'] == 'user_123'
                    assert result['email'] == 'test@example.com'
                    assert result['name'] == 'Test User'
                    assert result['avatar_url'] == 'https://example.com/avatar.jpg'
    
    def test_returns_none_on_expired_token(self):
        """Should return None when token is expired."""
        import jwt
        
        with patch.dict(os.environ, {'CLERK_JWKS_URL': 'https://example.com/.well-known/jwks.json'}):
            with patch('auth.clerk_auth._get_jwks_client') as mock_client:
                mock_key = MagicMock()
                mock_key.key = 'fake_key'
                mock_client.return_value.get_signing_key_from_jwt.return_value = mock_key
                
                with patch('jwt.decode', side_effect=jwt.ExpiredSignatureError("Token expired")):
                    from auth.clerk_auth import verify_clerk_token, AuthFailureReason
                    result, failure_reason = verify_clerk_token("expired.jwt.token")
                    assert result is None
                    assert failure_reason == AuthFailureReason.TOKEN_EXPIRED


class TestGenerateTenantId:
    """Tests for deterministic tenant_id generation."""
    
    def test_generates_slug_from_email_local_part(self):
        """Should slugify email local part for tenant_id."""
        from auth.clerk_auth import generate_tenant_id
        
        assert generate_tenant_id("john.doe@example.com") == "johndoe"
        assert generate_tenant_id("testuser@gmail.com") == "testuser"
        assert generate_tenant_id("user123@company.co") == "user123"
    
    def test_handles_special_characters(self):
        """Should remove special characters from slug."""
        from auth.clerk_auth import generate_tenant_id
        
        result = generate_tenant_id("test+user@example.com")
        assert result == "testuser"
        
        result = generate_tenant_id("test.user_123@example.com")
        assert result == "testuser123"
    
    def test_uses_hash_for_short_slugs(self):
        """Should use hash when slug is too short."""
        from auth.clerk_auth import generate_tenant_id
        
        result = generate_tenant_id("ab@example.com")
        assert len(result) == 12
    
    def test_uses_hash_for_invalid_email(self):
        """Should use hash for invalid email format."""
        from auth.clerk_auth import generate_tenant_id
        
        result = generate_tenant_id("notanemail")
        assert len(result) == 12


class TestUpsertClerkUser:
    """Tests for user upsert and role mapping."""
    
    @pytest.fixture
    def mock_db_pool(self):
        """Mock database pool."""
        with patch('db.db_pool') as mock:
            mock.connection_pool = MagicMock()
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock.get_connection.return_value.__exit__ = MagicMock(return_value=False)
            yield mock, mock_cursor
    
    def test_sets_admin_role_for_admin_emails(self, mock_db_pool):
        """Should set role='admin' for emails in ADMIN_EMAILS."""
        mock_pool, mock_cursor = mock_db_pool
        mock_cursor.fetchone.return_value = (
            1, 'user_123', 'admin@company.com', 'Admin User', 
            None, 'admin', None, None, None
        )
        
        with patch.dict(os.environ, {'ADMIN_EMAILS': 'admin@company.com,boss@company.com'}):
            import db
            result = db.upsert_clerk_user(
                clerk_user_id='user_123',
                email='admin@company.com',
                name='Admin User'
            )
            
            assert result['role'] == 'admin'
    
    def test_sets_client_role_for_non_admin(self, mock_db_pool):
        """Should set role='client' for non-admin emails."""
        mock_pool, mock_cursor = mock_db_pool
        mock_cursor.fetchone.return_value = (
            2, 'user_456', 'user@example.com', 'Regular User',
            None, 'client', 'user', None, None
        )
        
        with patch.dict(os.environ, {'ADMIN_EMAILS': 'admin@company.com'}):
            import db
            result = db.upsert_clerk_user(
                clerk_user_id='user_456',
                email='user@example.com',
                name='Regular User'
            )
            
            assert result['role'] == 'client'
    
    def test_generates_tenant_id_for_clients(self, mock_db_pool):
        """Should generate tenant_id for client users."""
        mock_pool, mock_cursor = mock_db_pool
        mock_cursor.fetchone.return_value = (
            3, 'user_789', 'client@example.com', 'Client User',
            None, 'client', 'client', None, None
        )
        
        with patch.dict(os.environ, {'ADMIN_EMAILS': ''}):
            with patch('db.ensure_tenant_exists', return_value=True):
                import db
                result = db.upsert_clerk_user(
                    clerk_user_id='user_789',
                    email='client@example.com',
                    name='Client User'
                )
                
                assert result['tenant_id'] == 'client'


class TestGetAuthUserFromRequest:
    """Tests for extracting auth user from request."""
    
    def test_extracts_token_from_bearer_header(self):
        """Should extract token from Authorization: Bearer header."""
        from auth.clerk_auth import get_auth_user_from_request
        
        mock_request = MagicMock()
        mock_request.headers = {'Authorization': 'Bearer test.jwt.token', 'Cookie': ''}
        mock_request.path = '/api/check-auth'
        
        mock_user = {'clerk_user_id': 'user_123', 'email': 'test@example.com'}
        
        with patch('auth.clerk_auth.verify_clerk_token') as mock_verify:
            mock_verify.return_value = (mock_user, None)
            
            result = get_auth_user_from_request(mock_request)
            
            mock_verify.assert_called_once_with('test.jwt.token')
            assert result['clerk_user_id'] == 'user_123'
    
    def test_extracts_token_from_session_cookie(self):
        """Should extract token from __session cookie."""
        from auth.clerk_auth import get_auth_user_from_request
        
        mock_request = MagicMock()
        mock_request.headers = {'Authorization': '', 'Cookie': '__session=cookie.jwt.token'}
        mock_request.path = '/api/check-auth'
        
        mock_user = {'clerk_user_id': 'user_456', 'email': 'cookie@example.com'}
        
        with patch('auth.clerk_auth.verify_clerk_token') as mock_verify:
            mock_verify.return_value = (mock_user, None)
            
            result = get_auth_user_from_request(mock_request)
            
            mock_verify.assert_called_once_with('cookie.jwt.token')
            assert result['clerk_user_id'] == 'user_456'
    
    def test_returns_none_when_no_token(self):
        """Should return None when no token is present."""
        from auth.clerk_auth import get_auth_user_from_request
        
        mock_request = MagicMock()
        mock_request.headers = {'Authorization': '', 'Cookie': ''}
        mock_request.path = '/api/check-auth'
        
        result = get_auth_user_from_request(mock_request, record_failure=False)
        assert result is None
