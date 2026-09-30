// Persistenz fuer users.json (Accounts + Sessions, enthaelt die Cookies).
//
// Ausgelegt fuer Aufrufe aus dem Request-Pfad, nicht nur aus dem
// SessionSelector: am 2026-09-30 hat ChatGPT ein Stundenlimit ausgespielt
// ("You've reached our limit of messages per hour", Cooldown ~60 min). Der
// Provider-Cooldown wurde nur im RAM gesetzt (utils/rate-limiter.js, fluechtiges
// _state), users.json blieb unberuehrt. Nach einem Proxy-Neustart war die
// Sperre damit vergessen und der naechste Request lief wieder ins 429, statt
// sofort zu warten.
//
// waitUntil ist ein Zeitstempel in ms. Der SessionSelector wertet ihn beim
// Start aus (core/session-selector.js) und ueberspringt gesperrte Konten.

const fs = require('fs')
const path = require('path')

const DATA_DIR = path.join(__dirname, '..', 'temp')
const USERS_FILE = path.join(DATA_DIR, 'users.json')

/**
 * Setzt waitUntil/waitReason eines Kontos und schreibt users.json atomar.
 * Fehler werden geloggt, aber nicht geworfen: ein Persistenzfehler darf einen
 * laufenden Request nicht abbrechen — schlimmstenfalls ist die Sperre nach
 * einem Neustart eben wieder weg.
 *
 * @param {object|null} userData - Referenz auf all[provider][username]
 * @param {string} provider
 * @param {string} username
 * @param {number} ms - verbleibende Sperrzeit
 * @param {string} reason
 * @returns {boolean} true, wenn geschrieben wurde
 */
function setAccountCooldown(userData, provider, username, ms, reason) {
  if (!userData) return false
  try {
    const waitUntil = Date.now() + Math.max(0, ms)
    userData.waitUntil = waitUntil
    userData.waitReason = reason

    const all = JSON.parse(fs.readFileSync(USERS_FILE, 'utf8'))
    if (!all[provider]) all[provider] = {}
    all[provider][username] = userData

    const tmp = USERS_FILE + '.tmp'
    fs.writeFileSync(tmp, JSON.stringify(all, null, 2), 'utf8')
    fs.renameSync(tmp, USERS_FILE)
    return true
  } catch (e) {
    console.error('[users] Cooldown nicht persistiert:', e.message)
    return false
  }
}

/**
 * Hebt eine persistierte Sperre auf (z. B. wenn ein 200 danach kam).
 *
 * @param {object|null} userData
 * @param {string} provider
 * @param {string} username
 */
function clearAccountCooldown(userData, provider, username) {
  if (!userData || !userData.waitUntil) return false
  try {
    delete userData.waitUntil
    delete userData.waitReason
    const all = JSON.parse(fs.readFileSync(USERS_FILE, 'utf8'))
    if (all[provider] && all[provider][username]) {
      delete all[provider][username].waitUntil
      delete all[provider][username].waitReason
      const tmp = USERS_FILE + '.tmp'
      fs.writeFileSync(tmp, JSON.stringify(all, null, 2), 'utf8')
      fs.renameSync(tmp, USERS_FILE)
    }
    return true
  } catch (e) {
    console.error('[users] Cooldown nicht geloescht:', e.message)
    return false
  }
}

module.exports = { setAccountCooldown, clearAccountCooldown, USERS_FILE }
