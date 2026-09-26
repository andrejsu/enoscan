FROM golang:1.23-alpine AS build

ARG MINIO_RELEASE=RELEASE.2025-03-12T18-04-18Z

RUN apk add --no-cache git
WORKDIR /src
RUN git clone --depth 1 --branch "$MINIO_RELEASE" https://github.com/minio/minio.git .
RUN CGO_ENABLED=0 go build -trimpath -ldflags "-s -w" -o /out/minio .

FROM alpine:3.22

RUN apk add --no-cache ca-certificates
COPY --from=build /out/minio /usr/bin/minio

EXPOSE 9000
ENTRYPOINT ["/usr/bin/minio"]
CMD ["server", "/data"]
