import React, { useState } from 'react'
import Modal from '../ui/Modal'
import Input from '../ui/Input'
import Button from '../ui/Button'

export default function PasswordModal({ open, onSubmit, error, loading }) {
  const [pw, setPw] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    onSubmit(pw)
  }

  return (
    <Modal open={open} title="Gallery is Protected" onClose={() => {}}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <p className="text-sm text-muted">
          This gallery requires a password. Please enter it below to view the photos.
        </p>
        <Input
          type="password"
          placeholder="Enter gallery password"
          value={pw}
          onChange={(e) => setPw(e.target.value)}
          error={error}
          autoFocus
        />
        <Button type="submit" loading={loading} className="w-full">
          Unlock Gallery
        </Button>
      </form>
    </Modal>
  )
}
