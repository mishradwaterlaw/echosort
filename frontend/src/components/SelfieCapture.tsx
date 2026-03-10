'use client'

import { useRef, useState, useEffect } from 'react'

export default function SelfieCapture({ 
  eventId, 
  getTokenAction,
  onSuccess
}: { 
  eventId: string, 
  getTokenAction: () => Promise<string | undefined>,
  onSuccess: (requestId: string) => void
}) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [stream, setStream] = useState<MediaStream | null>(null)
  const [capturedImage, setCapturedImage] = useState<Blob | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [isCameraActive, setIsCameraActive] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Cleanup stream on unmount
  useEffect(() => {
    return () => {
      if (stream) {
        stream.getTracks().forEach(track => track.stop())
      }
    }
  }, [stream])

  const startCamera = async () => {
    setError(null)
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({ 
        video: { facingMode: 'user' } 
      })
      setStream(mediaStream)
      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream
      }
      setIsCameraActive(true)
      setCapturedImage(null)
      setPreviewUrl(null)
    } catch (err: any) {
      setError('Could not access camera. Please allow camera permissions.')
      console.error(err)
    }
  }

  const stopCamera = () => {
    if (stream) {
      stream.getTracks().forEach(track => track.stop())
      setStream(null)
    }
    setIsCameraActive(false)
  }

  const captureFrame = () => {
    if (!videoRef.current) return

    const canvas = document.createElement('canvas')
    canvas.width = videoRef.current.videoWidth
    canvas.height = videoRef.current.videoHeight
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.drawImage(videoRef.current, 0, 0)

    canvas.toBlob((blob) => {
      if (blob) {
        setCapturedImage(blob)
        setPreviewUrl(URL.createObjectURL(blob))
        stopCamera()
      }
    }, 'image/jpeg', 0.9)
  }

  const retake = () => {
    setCapturedImage(null)
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
    }
    startCamera()
  }

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null)
    const file = e.target.files?.[0]
    if (!file) return

    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      setError('Invalid file type. Only JPEG, PNG, and WebP are allowed.')
      return
    }

    if (file.size > 15 * 1024 * 1024) {
      setError('File too large. Maximum size is 15MB.')
      return
    }

    setCapturedImage(file)
    setPreviewUrl(URL.createObjectURL(file))
    stopCamera()
  }

  const uploadSelfie = async () => {
    if (!capturedImage) return
    setUploading(true)
    setError(null)

    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
    }

    try {
      const token = await getTokenAction()
      if (!token) throw new Error("Authentication failed. Please log in again.")

      const formData = new FormData()
      formData.append('selfie', capturedImage, 'selfie.jpg')

      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const res = await fetch(`${apiUrl}/events/${eventId}/match`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      })

      if (!res.ok) {
        const errorData = await res.json().catch(() => null)
        throw new Error(errorData?.detail || 'Failed to upload selfie')
      }

      const data = await res.json()
      if (data.request_id) {
        onSuccess(data.request_id)
      } else {
        throw new Error('No valid response received from server')
      }
    } catch (err: any) {
      setError(err.message || 'Error communicating with server')
      setUploading(false)
    }
  }

  return (
    <div className="flex flex-col items-center w-full max-w-md mx-auto space-y-6">
      
      {error && (
        <div className="bg-red-50 text-red-600 px-4 py-3 rounded-xl border border-red-200 w-full text-sm font-medium text-center">
          {error}
        </div>
      )}

      {!isCameraActive && !capturedImage && (
        <div className="w-full flex flex-col space-y-3">
          <button 
            onClick={startCamera}
            className="w-full py-4 bg-[var(--rose)] text-white rounded-xl font-semibold shadow-md hover:opacity-90 transition-opacity flex items-center justify-center gap-2"
          >
            <span className="text-xl">📷</span> Open Camera
          </button>

          <div className="relative flex items-center py-4">
            <div className="flex-grow border-t border-[var(--border)]"></div>
            <span className="flex-shrink-0 mx-4 text-[var(--text-muted)] text-sm">OR</span>
            <div className="flex-grow border-t border-[var(--border)]"></div>
          </div>

          <label className="w-full py-4 bg-[var(--space)] border border-[var(--border)] text-[var(--text-primary)] rounded-xl font-semibold text-center cursor-pointer hover:border-[var(--rose)] transition-colors block">
            Upload from device
            <input 
              type="file" 
              accept="image/jpeg, image/png, image/webp" 
              onChange={handleFileUpload} 
              className="hidden" 
            />
          </label>
        </div>
      )}

      {isCameraActive && (
        <div className="w-full space-y-4">
          <div className="relative rounded-2xl overflow-hidden bg-black aspect-[3/4] sm:aspect-video w-full border border-[var(--border)]">
            <video 
              ref={videoRef} 
              autoPlay 
              playsInline 
              muted 
              className="w-full h-full object-cover mirror"
              style={{ transform: 'scaleX(-1)' }} // Mirror selfie view
            />
          </div>
          <div className="flex gap-3">
            <button 
              onClick={captureFrame}
              className="flex-1 py-4 bg-[var(--rose)] text-white rounded-xl font-bold shadow-md hover:opacity-90 transition-opacity"
            >
              Take Photo
            </button>
            <button 
              onClick={stopCamera}
              className="px-6 py-4 bg-[var(--charcoal)] text-[var(--text-primary)] rounded-xl font-semibold hover:bg-[var(--space)] border border-[var(--border)] transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {capturedImage && previewUrl && (
        <div className="w-full space-y-4">
          <div className="relative rounded-2xl overflow-hidden aspect-[3/4] sm:aspect-video w-full border border-[var(--border)] bg-[#0a0a0a]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img 
              src={previewUrl} 
              alt="Captured selfie" 
              className="w-full h-full object-contain"
            />
          </div>
          
          <div className="flex flex-col gap-3">
            <button 
              onClick={uploadSelfie}
              disabled={uploading}
              className="w-full py-4 bg-[var(--rose)] text-white rounded-xl font-bold shadow-md hover:opacity-90 disabled:opacity-50 transition-opacity relative"
            >
              {uploading ? 'Processing...' : 'Find My Photos'}
            </button>
            
            <button 
              onClick={retake}
              disabled={uploading}
              className="w-full py-3 bg-transparent text-[var(--text-muted)] rounded-xl font-medium hover:text-[var(--text-primary)] hover:bg-[var(--space)] transition-colors border border-transparent hover:border-[var(--border)] disabled:opacity-50"
            >
              Retake Photo
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
