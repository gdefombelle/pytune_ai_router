# Variables
$serviceName = "pytune_ai_router"
$remoteServer = "gabriel@195.201.9.184"
$imageName = "gdefombelle/" + $serviceName + ":latest"

Write-Host "🔨  Building Docker image..."
docker build --no-cache -t $imageName .

Write-Host "🚀  Pushing image to Docker Hub..."
docker push $imageName

Write-Host "🔄  Deploying on remote server..."

$remoteCommand = "docker stop $serviceName || true && docker rm $serviceName || true && docker pull $imageName && docker run -d --name $serviceName --network pytune_network --env-file /home/gabriel/pytune.env -v /var/log/pytune:/var/log/pytune --restart always $imageName"

ssh $remoteServer $remoteCommand

Write-Host "✅  $serviceName déployé avec succès !"
