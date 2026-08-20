import { useEffect, useState } from 'react'
import { addPerson, deleteEnrichment, deletePerson, getProfile, saveProfile } from './api'

// section key -> [field, label] pairs (no contact / sensitive fields by design)
const SECTIONS = [
  ['education', 'Education', [['institution', 'Institution'], ['degree', 'Degree'],
    ['field', 'Field'], ['start_year', 'Start year'], ['end_year', 'End year']]],
  ['experience', 'Experience', [['organization', 'Organization'], ['title', 'Title'],
    ['start', 'Start'], ['end', 'End']]],
  ['skills', 'Skills', [['name', 'Skill']]],
  ['activities', 'Activities', [['organization', 'Organization'], ['role', 'Role']]],
  ['projects', 'Projects', [['title', 'Title'], ['description', 'Description']]],
]

const EMPTY = {
  name: '', linkedin_url: '', company: '', position: '', location: '', notes: '',
  sections: Object.fromEntries(SECTIONS.map(([k]) => [k, []])),
}

/** `personId === null` → "Add person" mode. */
export default function ProfileEditor({ personId, onClose, onSaved }) {
  const [form, setForm] = useState(EMPTY)
  const [meta, setMeta] = useState({ manual: personId === null, updated_at: '' })
  const [busy, setBusy] = useState(!!personId)
  const [err, setErr] = useState(null)

  useEffect(() => {
    if (!personId) return
    getProfile(personId)
      .then((p) => {
        setForm({
          name: p.name ?? '', linkedin_url: p.linkedin_url ?? '',
          company: p.company ?? '', position: p.position ?? '',
          location: p.location ?? '', notes: p.notes ?? '',
          sections: Object.fromEntries(
            SECTIONS.map(([k]) => [k, p.sections?.[k] ?? []])
          ),
        })
        setMeta({ manual: p.manual, updated_at: p.updated_at })
      })
      .catch((e) => setErr(e.message))
      .finally(() => setBusy(false))
  }, [personId])

  const field = (k) => ({
    value: form[k],
    onChange: (e) => setForm((f) => ({ ...f, [k]: e.target.value })),
  })
  const rows = (key) => form.sections[key] ?? []
  const setRows = (key, next) =>
    setForm((f) => ({ ...f, sections: { ...f.sections, [key]: next } }))

  const run = async (fn) => {
    setBusy(true)
    setErr(null)
    try {
      await fn()
      onSaved?.()
      onClose()
    } catch (e) {
      setErr(e.message)
      setBusy(false)
    }
  }

  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <b>{personId ? 'Edit profile' : 'Add person'}</b>
          <span className="muted">
            manual entry · stored locally{meta.updated_at ? ` · updated ${meta.updated_at}` : ''}
          </span>
          <button className="ghost" onClick={onClose}>close</button>
        </header>

        <div className="modal-body">
          {err && <p className="error">{err}</p>}
          <div className="grid2">
            <Field label="Name"><input {...field('name')} /></Field>
            <Field label="LinkedIn URL"><input {...field('linkedin_url')} placeholder="https://www.linkedin.com/in/…" /></Field>
            <Field label="Current company"><input {...field('company')} /></Field>
            <Field label="Current position"><input {...field('position')} /></Field>
            <Field label="Location (optional)"><input {...field('location')} /></Field>
            <Field label="Short notes (optional)"><input {...field('notes')} /></Field>
          </div>

          {SECTIONS.map(([key, title, fields]) => (
            <section key={key} className="sect">
              <div className="sect-head">
                <b>{title}</b>
                <button
                  className="ghost"
                  onClick={() =>
                    setRows(key, [...rows(key), Object.fromEntries(fields.map(([f]) => [f, '']))])
                  }
                >
                  + add
                </button>
              </div>
              {rows(key).map((row, i) => (
                <div className="sect-row" key={i}>
                  {fields.map(([f, label]) => (
                    <input
                      key={f}
                      placeholder={label}
                      value={row[f] ?? ''}
                      onChange={(e) => {
                        const next = rows(key).slice()
                        next[i] = { ...next[i], [f]: e.target.value }
                        setRows(key, next)
                      }}
                    />
                  ))}
                  <button
                    className="ghost"
                    onClick={() => setRows(key, rows(key).filter((_, j) => j !== i))}
                  >
                    ×
                  </button>
                </div>
              ))}
            </section>
          ))}
        </div>

        <footer className="modal-foot">
          <button
            className="primary"
            disabled={busy}
            onClick={() =>
              run(() => (personId ? saveProfile(personId, form) : addPerson(form)))
            }
          >
            {busy ? 'saving…' : 'Save'}
          </button>
          {personId && (
            <button className="ghost" disabled={busy} onClick={() => run(() => deleteEnrichment(personId))}>
              Delete enrichment
            </button>
          )}
          {personId && meta.manual && (
            <button className="danger" disabled={busy} onClick={() => run(() => deletePerson(personId))}>
              Delete person
            </button>
          )}
          <span className="muted small">
            No email/phone fields. Nothing leaves this machine.
          </span>
        </footer>
      </div>
    </div>
  )
}

function Field({ label, children }) {
  return (
    <label className="fld">
      <span>{label}</span>
      {children}
    </label>
  )
}
