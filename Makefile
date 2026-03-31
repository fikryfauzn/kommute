.PHONY: build run test clean

build:
	go build -o bin/kommute ./cmd/kommute

run: build
	./bin/kommute

test:
	go test ./... -v

clean:
	rm -rf bin/
