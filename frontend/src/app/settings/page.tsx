"use client";
import { useEffect, useState } from "react";
import { fetchMetaStatus, fetchMetaAccounts, selectMetaAccount, disconnectMeta } from "@/lib/api";

interface AdAccount {
  id: string;
  name: string;
  status: string;
  currency: string;
  business: string;
  selected: boolean;
}

interface MetaStatus {
  connected: boolean;
  user_name?: string;
  selected_account?: string;
}

export default function SettingsPage() {
  const [metaStatus, setMetaStatus] = useState<MetaStatus | null>(null);
  const [accounts, setAccounts] = useState<AdAccount[]>([]);
  const [loadingAccounts, setLoadingAccounts] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchMetaStatus().then(setMetaStatus);
    // Check URL params for OAuth callback result
    const params = new URLSearchParams(window.location.search);
    if (params.get("meta_connected")) {
      fetchMetaStatus().then(setMetaStatus);
      loadAccounts();
    }
  }, []);

  async function loadAccounts() {
    setLoadingAccounts(true);
    try {
      const data = await fetchMetaAccounts();
      setAccounts(data.accounts);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingAccounts(false);
    }
  }

  async function handleSelectAccount(accountId: string) {
    setSaving(true);
    try {
      await selectMetaAccount(accountId);
      setAccounts(prev => prev.map(a => ({ ...a, selected: a.id === accountId })));
      const status = await fetchMetaStatus();
      setMetaStatus(status);
    } finally {
      setSaving(false);
    }
  }

  async function handleDisconnect() {
    await disconnectMeta();
    setMetaStatus({ connected: false });
    setAccounts([]);
  }

  return (
    <main className="max-w-2xl mx-auto py-10 px-4">
      <h1 className="text-2xl font-bold mb-8">⚙️ Configurações</h1>

      {/* Meta Ads */}
      <section className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold">Meta Ads</h2>
            <p className="text-sm text-gray-500">Conecte sua conta para importar dados de anúncios</p>
          </div>
          <span className={`px-3 py-1 rounded-full text-xs font-medium ${metaStatus?.connected ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
            {metaStatus?.connected ? "✅ Conectado" : "Desconectado"}
          </span>
        </div>

        {!metaStatus?.connected ? (
          <a
            href={`${process.env.NEXT_PUBLIC_API_URL}/auth/meta`}
            className="inline-flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg>
            Conectar com Facebook
          </a>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-gray-600">
              Conectado como <strong>{metaStatus.user_name}</strong>
            </p>
            {metaStatus.selected_account && (
              <p className="text-sm text-gray-600">
                Conta selecionada: <code className="bg-gray-100 px-1 rounded">{metaStatus.selected_account}</code>
              </p>
            )}
            <div className="flex gap-3">
              <button
                onClick={loadAccounts}
                disabled={loadingAccounts}
                className="px-4 py-2 bg-gray-100 rounded-lg text-sm hover:bg-gray-200 transition"
              >
                {loadingAccounts ? "Carregando..." : "Ver contas disponíveis"}
              </button>
              <button
                onClick={handleDisconnect}
                className="px-4 py-2 text-red-600 text-sm hover:text-red-700"
              >
                Desconectar
              </button>
            </div>

            {accounts.length > 0 && (
              <div className="mt-4">
                <p className="text-sm font-medium text-gray-700 mb-2">Selecione a conta de anúncios:</p>
                <div className="space-y-2">
                  {accounts.map((account) => (
                    <div
                      key={account.id}
                      onClick={() => !saving && handleSelectAccount(account.id)}
                      className={`flex items-center justify-between p-3 rounded-lg border cursor-pointer transition ${
                        account.selected
                          ? "border-blue-500 bg-blue-50"
                          : "border-gray-200 hover:border-gray-300 hover:bg-gray-50"
                      }`}
                    >
                      <div>
                        <p className="text-sm font-medium">{account.name}</p>
                        <p className="text-xs text-gray-500">
                          {account.id} • {account.currency} • {account.business}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`text-xs px-2 py-0.5 rounded-full ${account.status === "Ativa" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                          {account.status}
                        </span>
                        {account.selected && <span className="text-blue-500">✓</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* GHL */}
      <section className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">GoHighLevel</h2>
            <p className="text-sm text-gray-500">Location ID: vjZ5C77dlVyRlNKk44wh</p>
          </div>
          <span className="px-3 py-1 rounded-full text-xs font-medium bg-green-100 text-green-700">
            ✅ Configurado
          </span>
        </div>
      </section>
    </main>
  );
}
