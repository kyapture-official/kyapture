// C:/Users/LENOVO/Desktop/kyapture/frontend/src/pages/dashboard/SettingsPage.jsx
import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useAuthStore } from '../../store/authStore'
import { authApi } from '../../api/authApi'
import Button from '../../components/ui/Button'
import Input from '../../components/ui/Input'
import Spinner from '../../components/ui/Spinner'
import { useToast } from '../../components/ui/Toast'

export default function SettingsPage() {
  const { user, updateUser } = useAuthStore()
  const toast = useToast()

  const [profile, setProfile] = useState({
    display_name: user?.display_name || '',
    bio: user?.bio || '',
    username: user?.username || '',
    branding_color: user?.branding_color || '#111827',
  })
  
  const [logoURL, setLogoURL] = useState(user?.logo || null)
  const [pw, setPw] = useState({ old_password: '', new_password: '', new_password2: '' })

  // UI state-machine indicators
  const [savingProfile, setSavingProfile] = useState(false)
  const [savingPw, setSavingPw] = useState(false)
  const [logoUploading, setLogoUploading] = useState(false)
  const [pwErrors, setPwErrors] = useState({})

  // Flag to detect if user has modified their subdomain (username), triggering the warning banner
  const hasSubdomainChanged = profile.username.trim() !== (user?.username || '')

  // Form input change handlers optimized to prevent redundant garbage-collection sweeps
  const handleProfileChange = useCallback((e) => {
    const { name, value } = e.target
    setProfile((prev) => ({ ...prev, [name]: value }))
  }, [])

  const handlePasswordChange = useCallback((e) => {
    const { name, value } = e.target
    setPw((prev) => ({ ...prev, [name]: value }))
  }, [])

  const saveProfile = async (e) => {
    e.preventDefault()
    if (!profile.display_name.trim() || !profile.username.trim() || savingProfile) return

    setSavingProfile(true)
    try {
      // Subdomain normalization: enforce lowercase URL-safe characters
      const normalizedSubdomain = profile.username.trim().toLowerCase()
      const payload = {
        display_name: profile.display_name.trim(),
        bio: profile.bio.trim(),
        username: normalizedSubdomain,
        branding_color: profile.branding_color,
      }

      // Fixed: Removed destructured { data } since authApi returns the raw object directly
      const updatedUser = await authApi.updateMe(payload)
      updateUser(updatedUser)
      setProfile({
        display_name: updatedUser.display_name || '',
        bio: updatedUser.bio || '',
        username: updatedUser.username || '',
        branding_color: updatedUser.branding_color || '#111827',
      })
      toast('Profile updated!', 'success')
    } catch (err) {
      toast(err.response?.data?.username?.[0] || err.response?.data?.detail || 'Failed to save.', 'error')
    } finally {
      setSavingProfile(false)
    }
  }

  const handleLogoUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Secure 2MB logo size validation gate
    const MAX_SIZE = 2 * 1024 * 1024
    if (file.size > MAX_SIZE) {
      toast('Logo file exceeds the 2MB size limit.', 'error')
      return
    }

    setLogoUploading(true)
    
    // Build the multipart FormData payload
    const formData = new FormData()
    formData.append('logo', file)

    try {
      // Fixed: Removed destructured { data } since authApi returns the raw object directly
      const updatedUser = await authApi.updateMe(formData)
      updateUser(updatedUser)
      setLogoURL(updatedUser.logo)
      toast('Logo uploaded successfully!', 'success')
    } catch (err) {
      toast(err.response?.data?.logo?.[0] || 'Logo upload failed.', 'error')
    } finally {
      setLogoUploading(false)
    }
  }

  const handleLogoDelete = async () => {
    if (logoUploading) return
    setLogoUploading(true)

    try {
      // Fixed: Removed destructured { data } since authApi returns the raw object directly
      const updatedUser = await authApi.updateMe({ logo: null })
      updateUser(updatedUser)
      setLogoURL(null)
      toast('Logo removed successfully.', 'success')
    } catch (err) {
      toast('Failed to remove logo.', 'error')
    } finally {
      setLogoUploading(false)
    }
  }

  const savePassword = async (e) => {
    e.preventDefault()
    setPwErrors({})
    setSavingPw(true)
    try {
      await authApi.changePassword(pw)
      setPw({ old_password: '', new_password: '', new_password2: '' })
      toast('Password changed!', 'success')
    } catch (err) {
      setPwErrors(err.response?.data || {})
    } finally {
      setSavingPw(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-fade-up">
      {/* Header */}
      <div className="mb-8">
        <h1 className="font-serif text-4xl text-ink mb-1">Branding & Profile Settings</h1>
        <p className="text-sm text-muted">Manage your photographer profile, color identity, and logo.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Left Side: General Profile, Color, and Security forms */}
        <div className="lg:col-span-2 space-y-8">
          
          {/* Profile Card */}
          <div className="bg-white rounded-2xl border border-cream-200 p-6 shadow-sm">
            <h2 className="font-serif text-xl text-ink mb-5">Profile</h2>
            <form onSubmit={saveProfile} className="space-y-5">
              
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Input
                  label="Display name"
                  name="display_name"
                  value={profile.display_name}
                  onChange={handleProfileChange}
                  required
                />
                
                <Input
                  label="Username (subdomain)"
                  name="username"
                  value={profile.username}
                  onChange={handleProfileChange}
                  required
                  hint={`Your public URL: ${profile.username.trim().toLowerCase() || 'username'}.kyapture.com`}
                />
              </div>

              {/* Critical Subdomain Mutation Warning Banner */}
              {hasSubdomainChanged && (
                <div role="alert" className="p-4 bg-amber-50 border border-warm rounded-xl text-xs text-amber-800 space-y-1.5 leading-relaxed animate-fade-up">
                  <div className="flex items-center gap-1.5 font-semibold text-amber-900">
                    <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    Warning: Changing your Subdomain will rot existing links!
                  </div>
                  <p>
                    Updating your subdomain from <strong>"{user?.username}"</strong> to <strong>"{profile.username.trim().toLowerCase()}"</strong> 
                    will instantly break all shared links currently in use by your clients. They will no longer be able to access their galleries 
                    unless you share the newly compiled URL.
                  </p>
                </div>
              )}

              {/* Biography Textbox */}
              <div className="flex flex-col gap-1.5">
                <label htmlFor="bio-input" className="text-sm font-medium text-ink/80 block select-none">Biography</label>
                <textarea
                  id="bio-input"
                  name="bio"
                  value={profile.bio}
                  onChange={handleProfileChange}
                  className="w-full px-4 py-2.5 bg-cream-50/20 border border-cream-300 rounded-lg text-sm text-ink placeholder:text-muted focus:outline-none focus:border-cream-500 focus:ring-2 focus:ring-cream-200 resize-none transition-all duration-200"
                  rows={4}
                  placeholder="Tell your clients about yourself..."
                />
              </div>

              {/* Dynamic Branding Color Selector */}
              <div className="flex flex-col gap-1.5 max-w-xs">
                <label htmlFor="brand-color" className="text-sm font-medium text-ink/80 block select-none">
                  Portfolio Brand Color
                </label>
                <div className="flex items-center gap-3">
                  <input
                    type="color"
                    id="brand-color"
                    name="branding_color"
                    value={profile.branding_color}
                    onChange={handleProfileChange}
                    disabled={savingProfile}
                    className="w-10 h-10 border border-cream-300 rounded-lg cursor-pointer bg-transparent"
                  />
                  <input
                    type="text"
                    name="branding_color"
                    value={profile.branding_color}
                    onChange={handleProfileChange}
                    disabled={savingProfile}
                    className="w-24 px-3 py-1.5 text-sm uppercase rounded-lg border border-cream-300 bg-white font-mono focus:outline-none focus:border-cream-500"
                  />
                </div>
                <p className="text-[10px] text-muted font-light mt-1 leading-relaxed">
                  Applies dynamic styling highlights to your public collections and password gates.
                </p>
              </div>

              {/* Symmetrical Locked Email View */}
              <div className="pt-2">
                <p className="text-xs text-muted mb-1 select-none">Account Email (cannot be changed)</p>
                <p className="text-sm text-ink bg-cream-50 px-4 py-3 rounded-lg border border-cream-200/50 font-mono w-fit">{user?.email}</p>
              </div>

              <div className="pt-4 border-t border-cream-100 flex justify-end">
                <Button type="submit" loading={savingProfile}>
                  Save Profile Settings
                </Button>
              </div>
            </form>
          </div>

          {/* Password Card */}
          <div className="bg-white rounded-2xl border border-cream-200 p-6 shadow-sm">
            <h2 className="font-serif text-xl text-ink mb-5">Change Password</h2>
            <form onSubmit={savePassword} className="flex flex-col gap-4">
              <Input
                label="Current password"
                type="password"
                name="old_password"
                value={pw.old_password}
                onChange={handlePasswordChange}
                error={pwErrors.old_password?.[0]}
                required
              />
              <Input
                label="New password"
                type="password"
                name="new_password"
                value={pw.new_password}
                onChange={handlePasswordChange}
                error={pwErrors.new_password?.[0]}
                required
              />
              <Input
                label="Confirm new password"
                type="password"
                name="new_password2"
                value={pw.new_password2}
                onChange={handlePasswordChange}
                error={pwErrors.new_password2?.[0]}
                required
              />
              <div className="pt-4 border-t border-cream-100 flex justify-end">
                <Button type="submit" loading={savingPw}>
                  Change Password
                </Button>
              </div>
            </form>
          </div>

        </div>

        {/* Right Side: Professional Logo Upload Center */}
        <div className="lg:col-span-1">
          <div className="bg-white rounded-2xl border border-cream-200 p-6 shadow-sm flex flex-col items-center text-center space-y-6">
            <h3 className="text-sm font-semibold text-gray-900 tracking-wider uppercase">Business Logo</h3>

            {/* Logo Viewer Frame with Async Spinner */}
            <div className="relative w-32 h-32 rounded-2xl border border-cream-200 bg-cream-50/20 flex items-center justify-center overflow-hidden">
              {logoURL ? (
                <img src={logoURL} alt={profile.display_name} className="w-full h-full object-contain p-3 select-none pointer-events-none" />
              ) : (
                <svg className="w-10 h-10 text-cream-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
              )}

              {logoUploading && (
                <div className="absolute inset-0 bg-white/80 flex items-center justify-center">
                  <Spinner />
                </div>
              )}
            </div>

            <div className="space-y-3 w-full">
              <label className="block w-full text-center px-4 py-2.5 border border-cream-300 hover:border-cream-400 bg-white text-ink text-xs font-medium tracking-wide uppercase rounded-lg cursor-pointer transition-colors focus-within:ring-2 focus-visible:ring-ink">
                Upload New Logo
                <input
                  type="file"
                  accept="image/png, image/jpeg, image/webp"
                  onChange={handleLogoUpload}
                  disabled={logoUploading}
                  className="hidden"
                />
              </label>

              {logoURL && (
                <button
                  type="button"
                  onClick={handleLogoDelete}
                  disabled={logoUploading}
                  className="w-full text-center py-2 text-xs font-semibold text-red-600 hover:text-red-700 bg-transparent hover:bg-red-50 rounded-lg transition-colors cursor-pointer border border-transparent hover:border-red-100"
                >
                  Remove Logo
                </button>
              )}
            </div>

            <p className="text-[10px] text-muted leading-relaxed font-light select-none">
              Supports PNG, JPG, and WEBP. Maximum file size: 2MB. Logo appears dynamically at the top of your public gallery views.
            </p>
          </div>
        </div>

      </div>
    </div>
  )
}