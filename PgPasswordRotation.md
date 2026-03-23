az postgres flexible-server update --name kgpgsqlftjb -g rg-kg4-westus --admin-password YOUR_NEW_PASSWORD
az containerapp secret set --name mcp-server-ftjb -g rg-kg4-westus --secrets pg-password=YOUR_NEW_PASSWORD

$rev = az containerapp revision list --name mcp-server-ftjb -g rg-kg4-westus --query "[?properties.active].name" -o tsv
az containerapp revision restart --name mcp-server-ftjb -g rg-kg4-westus --revision $rev