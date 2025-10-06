FROM golang:alpine AS builder
ENV \
  CGO_ENABLED=1 \
  GOOS=linux \
  GOARCH=amd64
WORKDIR /build
COPY . .
RUN \
  apk add gcc musl-dev && \
  go build -o /app .

FROM alpine:latest AS final
COPY --from=builder /app /bin/app
CMD ["bin/app"]
