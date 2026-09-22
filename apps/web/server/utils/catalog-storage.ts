import { GetObjectCommand, NoSuchKey, S3Client } from '@aws-sdk/client-s3'

export interface StorageConfig {
  endpoint: string
  region: string
  accessKey: string
  secretKey: string
  imagesBucket: string
}

export interface StoredObject {
  body: ReadableStream<Uint8Array>
  contentType: string | undefined
  contentLength: number | undefined
}

let storageClient: S3Client | undefined

function getStorageClient(config: StorageConfig): S3Client {
  storageClient ??= new S3Client({
    endpoint: config.endpoint,
    region: config.region,
    forcePathStyle: true,
    credentials: {
      accessKeyId: config.accessKey,
      secretAccessKey: config.secretKey,
    },
  })
  return storageClient
}

export async function getImageObject(config: StorageConfig, key: string): Promise<StoredObject | null> {
  try {
    const response = await getStorageClient(config).send(new GetObjectCommand({
      Bucket: config.imagesBucket,
      Key: key,
    }))
    if (!response.Body) return null
    return {
      body: response.Body.transformToWebStream(),
      contentType: response.ContentType,
      contentLength: response.ContentLength,
    }
  }
  catch (error) {
    if (error instanceof NoSuchKey) return null
    throw error
  }
}
