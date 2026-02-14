/**
 * auth.js — MSAL.js 2.x wrapper for Entra ID authentication.
 *
 * Fetches public auth config from /auth/config, initialises
 * PublicClientApplication, and exposes login / logout / token helpers.
 */

// eslint-disable-next-line no-var
var Auth = (function () {
  "use strict";

  /** @type {msal.PublicClientApplication | null} */
  let msalInstance = null;
  /** @type {{ client_id: string, tenant_id: string, scopes: string[] } | null} */
  let authConfig = null;

  /**
   * Fetch the public auth configuration from the backend.
   * @returns {Promise<{ client_id: string, tenant_id: string, scopes: string[] }>}
   */
  async function fetchAuthConfig() {
    const res = await fetch("/auth/config");
    if (!res.ok) throw new Error("Failed to fetch auth config");
    return res.json();
  }

  /**
   * Initialise MSAL. Must be called once before any other auth method.
   */
  async function init() {
    authConfig = await fetchAuthConfig();

    const msalConfig = {
      auth: {
        clientId: authConfig.client_id,
        authority: `https://login.microsoftonline.com/${authConfig.tenant_id}`,
        redirectUri: window.location.origin,
      },
      cache: {
        cacheLocation: "sessionStorage",
        storeAuthStateInCookie: false,
      },
    };

    msalInstance = new msal.PublicClientApplication(msalConfig);
    await msalInstance.initialize();

    // Handle redirect promise (e.g. after a full-page redirect login)
    try {
      const response = await msalInstance.handleRedirectPromise();
      if (response) {
        msalInstance.setActiveAccount(response.account);
      }
    } catch (err) {
      console.error("MSAL redirect error:", err);
    }
  }

  /**
   * Interactive sign-in via popup.
   * @returns {Promise<msal.AccountInfo>}
   */
  async function login() {
    const loginRequest = {
      scopes: authConfig.scopes,
    };

    try {
      const response = await msalInstance.loginPopup(loginRequest);
      msalInstance.setActiveAccount(response.account);
      return response.account;
    } catch (err) {
      console.error("Login failed:", err);
      throw err;
    }
  }

  /**
   * Sign out the current user.
   */
  async function logout() {
    const account = msalInstance.getActiveAccount();
    if (account) {
      await msalInstance.logoutPopup({ account });
    }
  }

  /**
   * Get the currently signed-in account (or null).
   * @returns {msal.AccountInfo | null}
   */
  function getAccount() {
    if (!msalInstance) return null;
    const active = msalInstance.getActiveAccount();
    if (active) return active;

    // Fallback: pick the first account in the cache
    const accounts = msalInstance.getAllAccounts();
    if (accounts.length > 0) {
      msalInstance.setActiveAccount(accounts[0]);
      return accounts[0];
    }
    return null;
  }

  /**
   * Acquire an access token silently, falling back to popup.
   * @returns {Promise<string>} Bearer access token
   */
  async function getAccessToken() {
    const account = getAccount();
    if (!account) throw new Error("No signed-in user");

    const tokenRequest = {
      scopes: authConfig.scopes,
      account: account,
    };

    try {
      const response = await msalInstance.acquireTokenSilent(tokenRequest);
      return response.accessToken;
    } catch (err) {
      // Silent token acquisition failed — try popup
      console.warn("Silent token acquisition failed, falling back to popup:", err);
      const response = await msalInstance.acquireTokenPopup(tokenRequest);
      return response.accessToken;
    }
  }

  /**
   * Get the display name of the current user.
   * @returns {string}
   */
  function getUserDisplayName() {
    const account = getAccount();
    if (!account) return "";
    return account.name || account.username || "";
  }

  return {
    init,
    login,
    logout,
    getAccount,
    getAccessToken,
    getUserDisplayName,
  };
})();
