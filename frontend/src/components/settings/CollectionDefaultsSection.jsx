// File Location: frontend/src/components/settings/CollectionDefaultsSection.jsx
import { useEffect, useMemo, useState } from 'react'
import { useSubscription } from '../../hooks/useSubscription'
import { useToast } from '../ui/Toast'
import Button from '../ui/Button'
import UpgradePrompt from '../shared/UpgradePrompt'
import { COLOR_THEMES, LAYOUT_CLASSES } from '../../utils/designSettings'
import { TYPOGRAPHY_IDS } from '../../utils/typography'
import { useTypographyStyles } from '../../hooks/useTypographyStyles'
import { Card, ErrorBlock, InlineStatus, LoadingBlock, Switch } from './SettingsUI'
import { useUserSettings } from './useUserSettings'

const cap = (text) => text.charAt(0).toUpperCase() + text.slice(1)
const DESIGN_OPTIONS = {
  typography: { label: 'Typography', values: TYPOGRAPHY_IDS },
  colorPalette: { label: 'Colour palette', values: Object.keys(COLOR_THEMES) },
  layout: { label: 'Cover layout', values: Object.keys(LAYOUT_CLASSES) },
  gridStyle: { label: 'Grid style', values: ['vertical', 'horizontal'] },
  thumbSize: { label: 'Thumbnail size', values: ['regular', 'large'] },
}
const EMPTY_FORM = {
  is_published: false,
  is_downloadable: false,
  expiry_enabled: false,
  expires_in_days: 30,
  watermark_enabled: false,
  design: { typography: '', colorPalette: '', layout: '', gridStyle: '', thumbSize: '', gridSpacing: '' },
}

/** Server defaults -> editable form (anything the server doesn't hold stays at the app default). */
function toForm(defaults = {}) {
  return {
    is_published: Boolean(defaults.is_published),
    is_downloadable: Boolean(defaults.is_downloadable),
    expiry_enabled: Boolean(defaults.expires_in_days),
    expires_in_days: defaults.expires_in_days || 30,
    watermark_enabled: Boolean(defaults.watermark_enabled),
    design: { ...EMPTY_FORM.design, ...(defaults.design || {}) },
  }
}

/** Form -> the exact object the API stores. Unset design options are simply left out. */
function toPayload(form) {
  const design = {}
  for (const key of Object.keys(DESIGN_OPTIONS)) if (form.design[key]) design[key] = form.design[key]
  if (form.design.gridSpacing !== '' && form.design.gridSpacing !== null) design.gridSpacing = Number(form.design.gridSpacing)
  const payload = {
    is_published: form.is_published,
    is_downloadable: form.is_downloadable,
    expires_in_days: form.expiry_enabled ? Number(form.expires_in_days) : null,
    watermark_enabled: form.watermark_enabled,
  }
  if (Object.keys(design).length) payload.design = design
  return payload
}

export default function CollectionDefaultsSection() {
  const toast = useToast()
  const { settings, loading, loadError, reload, save } = useUserSettings()
  const { entitlements, loading: planLoading } = useSubscription()
  const { styles: typographyStyles } = useTypographyStyles()
  // Typography names come from the server's table once it has answered.
  const optionLabel = (key, value) =>
    (key === 'typography' && typographyStyles.find((style) => style.id === value)?.label) || cap(value)

  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState(null)
  const [errors, setErrors] = useState({})

  // The form always mirrors what the server holds (initial load and after each save).
  useEffect(() => {
    if (settings) setForm(toForm(settings.collection_defaults))
  }, [settings])

  const savedPayload = useMemo(() => JSON.stringify(toPayload(toForm(settings?.collection_defaults))), [settings])
  const dirty = JSON.stringify(toPayload(form)) !== savedPayload
  const watermarkLocked = !planLoading && !entitlements.watermark
  const hasAnySaved = settings && Object.keys(settings.collection_defaults || {}).length > 0

  const set = (key) => (value) => { setForm((prev) => ({ ...prev, [key]: value })); setStatus(null); setErrors({}) }
  const setDesign = (key) => (event) => {
    setForm((prev) => ({ ...prev, design: { ...prev.design, [key]: event.target.value } }))
    setStatus(null)
    setErrors({})
  }

  const submit = async (payload, successMessage) => {
    setSaving(true)
    setStatus(null)
    try {
      await save({ collection_defaults: payload })
      setErrors({})
      setStatus({ kind: 'success', message: successMessage })
      toast('Collection defaults saved', 'success')
    } catch (err) {
      setErrors(err.fieldErrors || {})
      setStatus({ kind: 'error', message: err.message || 'Please fix the highlighted settings.' })
    } finally {
      setSaving(false)
    }
  }

  const handleSave = (event) => {
    event.preventDefault()
    if (!dirty || saving) return
    if (form.expiry_enabled) {
      const days = Number(form.expires_in_days)
      if (!Number.isInteger(days) || days < 1 || days > 3650) {
        setErrors({ expires_in_days: 'Enter a whole number of days between 1 and 3650.' })
        return
      }
    }
    submit(toPayload(form), 'Collection defaults saved. They apply to collections you create from now on.')
  }

  const handleReset = () => submit({}, 'Defaults cleared. New collections start with the app\'s standard settings.')

  const selectClass = 'w-full rounded-lg border border-cream-200 bg-white px-3 py-2 text-sm text-ink focus:border-brand-green-500 focus:outline-none focus:ring-2 focus:ring-brand-green-500/10'

  return (
    <Card
      title="Collection defaults"
      description="Starting settings for NEW collections. They're applied once, when you create a collection — your existing collections are never changed, and you can still change any setting on an individual collection."
    >
      {loading ? (
        <LoadingBlock label="Loading your defaults…" />
      ) : loadError ? (
        <ErrorBlock message={loadError} onRetry={reload} />
      ) : (
        <form onSubmit={handleSave} noValidate className="space-y-6">
          <div className="space-y-3">
            <Switch
              id="defaults-published"
              label="Publish new collections immediately"
              description="Off: new collections start as drafts that only you can see."
              checked={form.is_published}
              onChange={set('is_published')}
              disabled={saving}
            />
            <Switch
              id="defaults-downloads"
              label="Allow client downloads"
              description="New collections let clients download photos (you can still add a download PIN per collection)."
              checked={form.is_downloadable}
              onChange={set('is_downloadable')}
              disabled={saving}
            />

            <div className="rounded-xl border border-cream-200 bg-cream-100/60 p-4">
              <Switch
                id="defaults-expiry"
                label="Expire new collections"
                description="Clients lose access this many days after you create the collection."
                checked={form.expiry_enabled}
                onChange={set('expiry_enabled')}
                disabled={saving}
              />
              {form.expiry_enabled && (
                <div className="mt-3 flex items-center gap-2">
                  <label htmlFor="defaults-expiry-days" className="text-xs font-medium text-ink/80">Days</label>
                  <input
                    id="defaults-expiry-days"
                    type="number"
                    min={1}
                    max={3650}
                    value={form.expires_in_days}
                    onChange={(e) => { set('expires_in_days')(e.target.value) }}
                    aria-invalid={errors.expires_in_days ? true : undefined}
                    className="w-28 rounded-lg border border-cream-200 bg-white px-3 py-1.5 text-sm focus:border-brand-green-500 focus:outline-none"
                  />
                </div>
              )}
              {errors.expires_in_days && <p role="alert" className="mt-2 text-xs text-red-600">{errors.expires_in_days}</p>}
            </div>

            {watermarkLocked && !form.watermark_enabled ? (
              <UpgradePrompt
                feature="watermark"
                message="Watermark new collections automatically."
              />
            ) : (
              <Switch
                id="defaults-watermark"
                label="Watermark new collections"
                description="Turns the watermark on for new collections (set its look per collection, in Watermark settings)."
                checked={form.watermark_enabled}
                onChange={set('watermark_enabled')}
                disabled={saving || planLoading}
              />
            )}
          </div>

          <fieldset className="space-y-3">
            <legend className="mb-1 text-sm font-medium text-ink">Design</legend>
            <p className="text-xs text-muted">Leave an option on “App default” to keep the standard look.</p>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {Object.entries(DESIGN_OPTIONS).map(([key, { label, values }]) => (
                <div key={key} className="flex flex-col gap-1">
                  <label htmlFor={`defaults-${key}`} className="text-xs font-semibold text-ink/80">{label}</label>
                  <select
                    id={`defaults-${key}`}
                    value={form.design[key]}
                    onChange={setDesign(key)}
                    disabled={saving}
                    aria-invalid={errors[`design.${key}`] ? true : undefined}
                    className={selectClass}
                  >
                    <option value="">App default</option>
                    {values.map((value) => <option key={value} value={value}>{optionLabel(key, value)}</option>)}
                  </select>
                  {errors[`design.${key}`] && <p role="alert" className="text-xs text-red-600">{errors[`design.${key}`]}</p>}
                </div>
              ))}
              <div className="flex flex-col gap-1">
                <label htmlFor="defaults-gridSpacing" className="flex justify-between text-xs font-semibold text-ink/80">
                  <span>Grid spacing</span>
                  <span className="font-mono font-normal text-muted">
                    {form.design.gridSpacing === '' ? 'App default' : `${form.design.gridSpacing}px`}
                  </span>
                </label>
                <input
                  id="defaults-gridSpacing"
                  type="range"
                  min={4}
                  max={32}
                  value={form.design.gridSpacing === '' ? 16 : form.design.gridSpacing}
                  onChange={setDesign('gridSpacing')}
                  disabled={saving}
                  className="w-full accent-brand-green-600"
                />
                {form.design.gridSpacing !== '' && (
                  <button
                    type="button"
                    onClick={() => setForm((prev) => ({ ...prev, design: { ...prev.design, gridSpacing: '' } }))}
                    className="self-start text-[11px] text-muted underline underline-offset-2 hover:text-ink"
                  >
                    Use app default
                  </button>
                )}
              </div>
            </div>
          </fieldset>

          <InlineStatus status={status} />

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-cream-200 pt-4">
            <button
              type="button"
              onClick={handleReset}
              disabled={saving || !hasAnySaved}
              className="cursor-pointer text-xs text-muted underline underline-offset-2 hover:text-ink disabled:cursor-not-allowed disabled:no-underline disabled:opacity-50"
            >
              Reset to app defaults
            </button>
            <Button type="submit" loading={saving} disabled={!dirty}>Save defaults</Button>
          </div>
        </form>
      )}
    </Card>
  )
}
