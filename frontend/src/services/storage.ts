import { ref, uploadBytesResumable, getDownloadURL } from 'firebase/storage'
import { storage } from '../lib/firebase'

export async function uploadUserFile(
  path: string,
  file: File,
  onProgress?: (progress: number) => void,
) {
  const fileRef = ref(storage, path)
  const uploadTask = uploadBytesResumable(fileRef, file)

  return new Promise<string>((resolve, reject) => {
    uploadTask.on(
      'state_changed',
      (snapshot) => {
        if (onProgress) {
          const progress = (snapshot.bytesTransferred / snapshot.totalBytes) * 100
          onProgress(Math.round(progress))
        }
      },
      (error) => reject(error),
      async () => {
        const url = await getDownloadURL(uploadTask.snapshot.ref)
        resolve(url)
      },
    )
  })
}
