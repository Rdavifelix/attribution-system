# Configurar App do Meta Ads

## 1. Criar o App

1. Acesse [developers.facebook.com](https://developers.facebook.com)
2. **My Apps → Create App**
3. Selecione **"Business"** como tipo
4. Nome: `Attribution System`
5. Business Account: selecione sua conta do Business Manager
6. Clique em **Create App**

## 2. Adicionar produtos

Na dashboard do app, clique em **Add Products** e adicione:
- **Facebook Login** (clique em Set Up)
- **Marketing API** (clique em Set Up)

## 3. Configurar Facebook Login

Vá em **Facebook Login → Settings**:
- **Valid OAuth Redirect URIs**: `http://localhost:8000/auth/meta/callback`
- Para produção: `https://seu-backend.railway.app/auth/meta/callback`
- Clique em **Save Changes**

## 4. Pegar App ID e App Secret

Vá em **Settings → Basic**:
- Copie o **App ID** → `META_APP_ID=`
- Clique em **Show** no App Secret → `META_APP_SECRET=`

## 5. Configurar permissões (Roles)

Vá em **App Review → Permissions and Features** e solicite:
- `ads_read` ← essencial
- `ads_management` ← para reports
- `business_management` ← para listar contas

> **Nota:** Para desenvolvimento/teste, você já tem acesso às suas próprias contas sem precisar de App Review. O App Review é necessário apenas para disponibilizar para outros usuários.

## 6. Atualizar .env

```env
META_APP_ID=1234567890
META_APP_SECRET=abc123def456
META_OAUTH_REDIRECT_URI=http://localhost:8000/auth/meta/callback
```

## 7. Testar o fluxo

1. Inicie o backend: `uvicorn backend.api.main:app --reload`
2. Acesse: `http://localhost:8000/auth/meta`
3. Autorize com sua conta do Facebook
4. Você será redirecionado de volta e verá suas contas disponíveis
