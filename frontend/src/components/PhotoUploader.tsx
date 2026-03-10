'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

/**
 * Question: Why do we validate file type and size on the client before sending to the API — even though the API also validates them?
 * Answer: Validating on the client provides immediate, interactive feedback to the user without making them wait for a potentially large upload to fail over the network. 
 * This saves both the user's bandwidth and server resources. If a user accidentally selects a 50MB file or a PDF instead of an image, 
 * catching it instantly via client-side validation is a vastly superior UX compared to watching a long upload progress bar only to get an error at the end.
 */

export default function PhotoUploader({ 
  eventId, 
  getTokenAction 
}: { 
  eventId: string, 
  getTokenAction: () => Promise<string | undefined> 
}) {
  const [files, setFiles] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState<{ [key: string]: number }>({})
  const [error, setError] = useState<string | null>(null)
  const router = useRouter()

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null)
    if (!e.target.files) return

    const selectedFiles = Array.from(e.target.files)
    const validFiles: File[] = []
    
    for (const file of selectedFiles) {
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
        setError(`Invalid file type: ${file.name}. Only JPEG, PNG, and WebP are allowed.`)
        return
      }
      if (file.size > 15 * 1024 * 1024) {
        setError(`File too large: ${file.name}. Maximum size is 15MB.`)
        return
      }
      validFiles.push(file)
    }

    setFiles(validFiles)
    
    // reset progress for new selection
    const initProgress: { [key: string]: number } = {}
    validFiles.forEach(f => { initProgress[f.name] = 0 })
    setProgress(initProgress)
  }

  const uploadFile = async (file: File, token: string): Promise<void> => {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      xhr.open('POST', `${apiUrl}/events/${eventId}/photos`, true)
      xhr.setRequestHeader('Authorization', `Bearer ${token}`)

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const percent = Math.round((e.loaded / e.total) * 100)
          setProgress(prev => ({ ...prev, [file.name]: percent }))
        }
      }

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          setProgress(prev => ({ ...prev, [file.name]: 100 }))
          resolve()
        } else {
          try {
            const data = JSON.parse(xhr.responseText)
            reject(new Error(data.detail || `Upload failed for ${file.name}`))
          } catch {
            reject(new Error(`Upload failed for ${file.name}`))
          }
        }
      }

      xhr.onerror = () => reject(new Error(`Network error uploading ${file.name}`))

      const formData = new FormData()
      formData.append('files', file) // Backend expects List[UploadFile]
      xhr.send(formData)
    })
  }

  const pollPhotos = (token: string) => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${apiUrl}/events/${eventId}/photos`, {
          headers: { 'Authorization': `Bearer ${token}` },
          cache: 'no-store'
        })
        if (res.ok) {
          const data = await res.json()
          const photos = data.photos || []
          router.refresh()
          
          if (photos.length > 0) {
            const allResolved = photos.every(
              (p: { embedding_status: string }) => 
                p.embedding_status === 'done' || p.embedding_status === 'failed'
            )
            if (allResolved) {
              clearInterval(interval)
            }
          }
        }
      } catch (err) {
        console.error("Polling error", err)
      }
    }, 4000)
  }

  const handleUpload = async () => {
    if (files.length === 0) return
    setUploading(true)
    setError(null)
    
    try {
      const token = await getTokenAction()
      if (!token) throw new Error("Authentication failed. Please log in again.")

      // Sequentially upload for UI stability and accurate per-file completion
      for (const file of files) {
        await uploadFile(file, token)
      }

      setFiles([])
      router.refresh()
      
      // Start polling for embedding completion
      pollPhotos(token)

    } catch (err: any) {
      setError(err.message || "Upload failed")
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="bg-[var(--space)] border border-[var(--border)] rounded-xl p-6 shadow-sm mt-8">
      <h3 className="text-lg font-medium text-[var(--text-primary)] mb-4">Upload Photos</h3>
      
      <div className="flex flex-col gap-4">
        <input 
          type="file" 
          multiple 
          accept="image/jpeg, image/png, image/webp"
          onChange={handleFileChange}
          disabled={uploading}
          className="text-sm text-[var(--text-muted)] file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-medium file:bg-[var(--charcoal)] file:text-[var(--text-primary)] hover:file:bg-[var(--border)] disabled:opacity-50 transition-colors"
        />

        {error && <p className="text-sm text-red-500 font-medium">{error}</p>}
        
        {files.length > 0 && (
          <div className="flex flex-col gap-3 mt-2 border border-[var(--border)] rounded-lg p-4 bg-[#0a0a0a]">
            <p className="text-sm text-[var(--text-muted)] font-medium mb-1">{files.length} file(s) selected</p>
            {files.map(f => (
              <div key={f.name} className="flex items-center gap-3 text-sm">
                <span className="truncate w-1/3 text-[var(--text-primary)]">{f.name}</span>
                <div className="flex-1 bg-[var(--charcoal)] h-2 rounded-full overflow-hidden">
                  <div 
                    className="bg-[var(--rose)] h-full transition-all duration-300"
                    style={{ width: `${progress[f.name] || 0}%` }}
                  />
                </div>
                <span className={`w-10 text-right text-xs font-medium ${progress[f.name] === 100 ? 'text-green-500' : 'text-[var(--text-muted)]'}`}>
                  {progress[f.name] || 0}%
                </span>
              </div>
            ))}
          </div>
        )}

        <button 
          onClick={handleUpload} 
          disabled={files.length === 0 || uploading}
          className="mt-2 bg-[var(--rose)] text-white px-6 py-2 rounded-lg font-medium shadow-sm hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-all w-fit"
        >
          {uploading ? 'Uploading...' : 'Start Upload'}
        </button>
      </div>
    </div>
  )
}
