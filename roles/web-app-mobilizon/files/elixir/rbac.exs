Logger.put_process_level(self(), :error)

%{
  "administrators" => administrators,
  "moderators" => moderators,
  "bootstrap" => bootstrap,
  "provider" => provider
} = Jason.decode!(IO.read(:stdio, :eof))

administrators = MapSet.new(administrators, &String.downcase/1)
moderators = moderators |> MapSet.new(&String.downcase/1) |> MapSet.difference(administrators)
bootstrap = String.downcase(bootstrap)

created =
  administrators
  |> MapSet.union(moderators)
  |> Enum.reject(&(&1 == bootstrap))
  |> Enum.filter(&match?({:error, :user_not_found}, Mobilizon.Users.get_user_by_email(&1)))
  |> Enum.map(fn email ->
    {:ok, _user} = Mobilizon.Users.create_external(email, provider)
    email
  end)

desired_role = fn email ->
  cond do
    MapSet.member?(administrators, email) -> :administrator
    MapSet.member?(moderators, email) -> :moderator
    true -> :user
  end
end

changed =
  Mobilizon.Users.User
  |> Mobilizon.Storage.Repo.all()
  |> Enum.filter(&(&1.provider == provider and String.downcase(&1.email) != bootstrap))
  |> Enum.map(&{&1, desired_role.(String.downcase(&1.email))})
  |> Enum.reject(fn {user, role} -> user.role == role end)
  |> Enum.map(fn {user, role} ->
    {:ok, _user} = Mobilizon.Users.update_user(user, %{role: role})
    user.email
  end)

IO.puts("MOBILIZON_RBAC=" <> if(created == [] and changed == [], do: "unchanged", else: "changed"))
