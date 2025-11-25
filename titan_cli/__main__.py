import typer

app = typer.Typer()

@app.command()
def main():
    """
    Prints a greeting message.
    """
    print("Hola Mundo")

if __name__ == "__main__":
    app()
