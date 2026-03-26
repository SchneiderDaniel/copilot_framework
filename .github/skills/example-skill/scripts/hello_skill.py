import sys

def main():
    print("Hello from the example-skill script!")
    if len(sys.argv) > 1:
        print(f"Arguments received: {sys.argv[1:]}")

if __name__ == "__main__":
    main()
