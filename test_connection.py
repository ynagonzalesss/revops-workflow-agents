from connectors_live import connect_from_env


def main():
    client = connect_from_env()
    result = client.query("SELECT Id, Name FROM Opportunity LIMIT 3")
    print(f"Connected. Found {result['totalSize']} opportunity(ies):")
    for record in result["records"]:
        print(f"  {record['Id']} — {record['Name']}")


if __name__ == "__main__":
    main()
