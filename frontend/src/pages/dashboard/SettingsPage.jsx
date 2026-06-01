import React, { useState } from 'react'
import { useAuthStore } from '../../store/authStore'
import { authApi } from '../../api/authApi'
import Button from '../../components/ui/Button'
import Input from '../../components/ui/Input'
import { useToast } from '../../components/ui/Toast'

export default function SettingsPage() {
  const { user, updateUser } = useAuthStore()
  const toast = useToast()

  const [profile, setProfile] = useState({
    display_name: user?.display_name || '',
    bio: user?.bio || '',
    username: user?.username || '',
  })
  const [pw, setPw] = useState({ old_password: '', new_password: '', new_password2: '' })
  const [savingProfile, setSavingProfile] = useState(false)
  const [savingPw, setSavingPw] = useState(false)
  const [pwErrors, setPwErrors] = useState({})

  const setP = (k) => (e) => setProfile((f) => ({ ...f, [k]: e.target.value }))
  const setW = (k) => (e) => setPw((f) => ({ ...f, [k]: e.target.value }))

  const saveProfile = async (e) => {
    e.preventDefault()
    setSavingProfile(true)
    try {
      const { data } = await authApi.updateMe(profile)
      updateUser(data)
      toast('Profile updated!', 'success')
    } catch (err) {
      toast(err.response?.data?.username?.[0] || 'Failed to save.', 'error')
    } finally {
      setSavingProfile(false)
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
    <div className="max-w-lg">
      <div className="mb-8 animate-fade-up">
        <h1 className="font-serif text-4xl text-ink mb-1">Settings</h1>
        <p className="text-sm text-muted">Manage your photographer profile.</p>
      </div>

      {/* Profile */}
      <div className="bg-white rounded-2xl border border-cream-200 p-6 mb-6 animate-fade-up delay-100">
        <h2 className="font-serif text-xl text-ink mb-5">Profile</h2>
        <form onSubmit={saveProfile} className="flex flex-col gap-4">
          <Input
            label="Display name"
            value={profile.display_name}
            onChange={setP('display_name')}
            placeholder=""
          />
          <Input
            label="Username (subdomain)"
            value={profile.username}
            onChange={setP('username')}
            hint={`Your public URL: ${profile.username}.kyapture.com`}
          />
          <div>
            <label className="text-sm font-medium text-ink/80 block mb-1">Bio</label>
            <textarea
              className="w-full px-4 py-2.5 bg-white border border-cream-300 rounded-lg text-sm text-ink placeholder:text-muted focus:outline-none focus:border-cream-500 focus:ring-2 focus:ring-cream-200 resize-none"
              rows={3}
              placeholder="Tell your clients about yourself..."
              value={profile.bio}
              onChange={setP('bio')}
            />
          </div>
          <div className="pt-1">
            <p className="text-xs text-muted mb-1">Email (cannot be changed)</p>
            <p className="text-sm text-ink bg-cream-100 px-4 py-2.5 rounded-lg">{user?.email}</p>
          </div>
          <Button type="submit" loading={savingProfile} className="w-fit">
            Save Profile
          </Button>
        </form>
      </div>

      {/* Password */}
      <div className="bg-white rounded-2xl border border-cream-200 p-6 animate-fade-up delay-200">
        <h2 className="font-serif text-xl text-ink mb-5">Change Password</h2>
        <form onSubmit={savePassword} className="flex flex-col gap-4">
          <Input
            label="Current password"
            type="password"
            value={pw.old_password}
            onChange={setW('old_password')}
            error={pwErrors.old_password?.[0]}
            required
          />
          <Input
            label="New password"
            type="password"
            value={pw.new_password}
            onChange={setW('new_password')}
            error={pwErrors.new_password?.[0]}
            required
          />
          <Input
            label="Confirm new password"
            type="password"
            value={pw.new_password2}
            onChange={setW('new_password2')}
            error={pwErrors.new_password2?.[0]}
            required
          />
          <Button type="submit" loading={savingPw} className="w-fit">
            Change Password
          </Button>
        </form>
      </div>
    </div>
  )
}
